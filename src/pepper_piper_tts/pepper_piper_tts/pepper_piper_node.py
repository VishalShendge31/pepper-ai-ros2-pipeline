	#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import os
import socket
import struct
import subprocess
import tempfile
import time
import signal
from contextlib import contextmanager

class PiperTTSNode(Node):
    def __init__(self):
        super().__init__('piper_tts')
        
        # Declare and get parameters
        self.declare_parameters(
            namespace='',
            parameters=[
                ('input_topic', 'openai_response'),
                ('voice_model', '/usr/local/share/piper/voices/de_DE-thorsten_emotional-medium.onnx'),
                ('pepper_ip', '192.168.100.20'), #put pepper ip address here
                ('tts_port', 5005),
                ('piper_binary', '/usr/local/bin/piper'),
                ('max_retries', 3),
                ('retry_delay', 2.0),
                ('timeout', 30.0)
            ]
        )
        
        # Get parameter values
        self.input_topic = self.get_parameter('input_topic').value
        self.voice_model = self.get_parameter('voice_model').value
        self.pepper_ip = self.get_parameter('pepper_ip').value
        self.tts_port = self.get_parameter('tts_port').value
        self.piper_binary = self.get_parameter('piper_binary').value
        self.max_retries = self.get_parameter('max_retries').value
        self.retry_delay = self.get_parameter('retry_delay').value
        self.timeout = self.get_parameter('timeout').value
        
        # Validate installation
        self._validate_installation()
        
        # Initialize socket connection to Pepper
        self.pepper_socket = None
        self._connect_to_pepper()
        
        # Subscribe to text input topic
        self.subscription = self.create_subscription(
            String,
            self.input_topic,
            self._tts_callback,
            10)
        
        self.get_logger().info(f'Piper TTS node initialized')
        self.get_logger().info(f'- Voice model: {self.voice_model}')
        self.get_logger().info(f'- Pepper IP: {self.pepper_ip}:{self.tts_port}')
        self.get_logger().info(f'- Listening on: {self.input_topic}')

    def _validate_installation(self):
        """Verify Piper installation is working correctly before starting"""
        # Check if Piper binary exists
        if not os.path.exists(self.piper_binary):
            self.get_logger().fatal(f'Piper binary not found at {self.piper_binary}')
            self.get_logger().fatal('Please run the installation steps from the documentation')
            raise RuntimeError('Piper binary not installed')
        
        # Check if voice model exists
        if not os.path.exists(self.voice_model):
            self.get_logger().fatal(f'Voice model not found at {self.voice_model}')
            self.get_logger().fatal('Please verify your voice model installation')
            raise FileNotFoundError(f'Voice model not found: {self.voice_model}')
        
        # Check if JSON config exists
        json_path = f"{self.voice_model}.json"
        if not os.path.exists(json_path):
            self.get_logger().warn(f'Voice config file not found at {json_path}')
            self.get_logger().warn('This may cause issues with pronunciation')
        
        # Perform a quick self-test
        self.get_logger().info('Performing Piper self-test...')
        try:
            test_process = subprocess.run(
                [self.piper_binary, '--model', self.voice_model],
                input='Test',
                capture_output=True,
                text=True,
                timeout=5,
                encoding='utf-8'
            )
            
            if test_process.returncode != 0:
                self.get_logger().error('Piper self-test failed!')
                self.get_logger().error(f'Error: {test_process.stderr}')
                raise RuntimeError('Piper self-test failed')
                
            self.get_logger().info('Piper self-test successful')
        except Exception as e:
            self.get_logger().fatal(f'Piper self-test failed: {str(e)}')
            raise

    def _connect_to_pepper(self):
        """Establish connection to Pepper with retry logic"""
        retry_count = 0
        
        while retry_count < self.max_retries:
            try:
                # Close existing connection if it exists
                if self.pepper_socket:
                    try:
                        self.pepper_socket.close()
                    except:
                        pass
                
                # Create new socket connection
                self.pepper_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.pepper_socket.settimeout(10.0)  # Connection timeout
                self.pepper_socket.connect((self.pepper_ip, self.tts_port))
                
                self.get_logger().info(f'Connected to Pepper at {self.pepper_ip}:{self.tts_port}')
                return
                
            except Exception as e:
                retry_count += 1
                self.get_logger().warn(f'Connection attempt {retry_count}/{self.max_retries} failed: {e}')
                
                if retry_count < self.max_retries:
                    time.sleep(self.retry_delay)
                else:
                    self.get_logger().fatal(f'Failed to connect to Pepper after {self.max_retries} attempts')
                    raise

    @contextmanager
    def _temp_wav_file(self):
        """Context manager for temporary WAV files with proper cleanup"""
        tmp_wav = None
        try:
            # Create temporary file that won't be auto-deleted
            tmp_wav = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            yield tmp_wav.name
        finally:
            # Clean up the temporary file
            if tmp_wav and os.path.exists(tmp_wav.name):
                try:
                    os.unlink(tmp_wav.name)
                except Exception as e:
                    self.get_logger().debug(f'Failed to clean up temp file: {e}')

    def _synthesize_speech(self, text):
        """Generate speech audio using Piper CLI"""
        with self._temp_wav_file() as wav_path:
            # Run Piper command
            cmd = [
                self.piper_binary,
                '--model', self.voice_model,
                '--output_file', wav_path
            ]
            
            self.get_logger().debug(f'Running Piper: {" ".join(cmd)}')
            
            try:
                # Start the process
                process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8'
                )
                
                # Send text and get output
                stdout, stderr = process.communicate(input=text, timeout=self.timeout)
                
                # Check for errors
                if process.returncode != 0:
                    error_msg = stderr.strip() or 'Unknown error'
                    self.get_logger().error(f'Piper failed with code {process.returncode}: {error_msg}')
                    return None
                
                # Check if WAV file was created
                if not os.path.exists(wav_path):
                    self.get_logger().error('Piper did not generate audio file')
                    return None
                
                # Read the generated audio
                with open(wav_path, 'rb') as f:
                    return f.read()
                    
            except subprocess.TimeoutExpired:
                self.get_logger().error('Piper process timed out')
                process.kill()
                return None
            except Exception as e:
                self.get_logger().error(f'Piper execution error: {e}')
                return None

    def _send_to_pepper(self, audio_data):
        """Send audio data to Pepper with retry logic"""
        if not self.pepper_socket:
            self.get_logger().warn('No active connection to Pepper')
            try:
                self._connect_to_pepper()
            except Exception as e:
                self.get_logger().error(f'Failed to reconnect: {e}')
                return False
        
        try:
            # Send audio size (8 bytes, big-endian)
            audio_size = len(audio_data)
            self.pepper_socket.sendall(struct.pack(">Q", audio_size))
            
            # Send audio data
            self.pepper_socket.sendall(audio_data)
            self.get_logger().info(f'Sent {audio_size:,} bytes of audio to Pepper')
            return True
            
        except (socket.error, BrokenPipeError) as e:
            self.get_logger().warn(f'Socket error: {e}. Attempting to reconnect...')
            try:
                self._connect_to_pepper()
                # Retry sending
                self.pepper_socket.sendall(struct.pack(">Q", audio_size))
                self.pepper_socket.sendall(audio_data)
                self.get_logger().info(f'Successfully sent audio after reconnect')
                return True
            except Exception as retry_e:
                self.get_logger().error(f'Failed to send audio after reconnect: {retry_e}')
                return False

    def _tts_callback(self, msg):
        """Process incoming text for TTS"""
        self.get_logger().info(f'Received text for TTS: "{msg.data}"')
        
        try:
            # Generate speech audio
            audio_data = self._synthesize_speech(msg.data)
            
            if not audio_data:
                self.get_logger().error('Failed to generate speech audio')
                return
                
            if len(audio_data) == 0:
                self.get_logger().error('Generated audio is empty')
                return
            
            # Send to Pepper
            if self._send_to_pepper(audio_data):
                self.get_logger().info('TTS processing completed successfully')
            else:
                self.get_logger().error('Failed to send audio to Pepper')
                
        except Exception as e:
            self.get_logger().error(f'TTS processing failed: {str(e)}')

    def destroy_node(self):
        """Clean up resources before node destruction"""
        if self.pepper_socket:
            try:
                self.pepper_socket.close()
            except:
                pass
            self.pepper_socket = None
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    
    try:
        node = PiperTTSNode()
        try:
            rclpy.spin(node)
        except KeyboardInterrupt:
            node.get_logger().info('Shutting down TTS node (keyboard interrupt)')
        finally:
            node.destroy_node()
            rclpy.shutdown()
    except Exception as e:
        print(f'Failed to start Piper TTS node: {e}')
        return 1

if __name__ == '__main__':
    exit(main())
