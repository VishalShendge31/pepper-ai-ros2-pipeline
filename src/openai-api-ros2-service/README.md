# 🤖 OpenAI ROS 2 Integration – GPT Chat Server

Welcome to the OpenAI Chat Server for ROS 2!  
This project allows ROS 2 nodes to interact directly with the OpenAI API — including context-aware conversations, dynamic model selection, and prompt pre-conditioning.

---

## 🧱 Project Structure

This repository contains two ROS 2 packages:

### 1. `openai_server_interfaces`
> Contains the service definition `OpenaiServer.srv`

```srv
string prompt
bool reset_conversation
string pre_prompt
---
string response
```

### 2. `openai_server`
> Contains the ROS 2 service server (in C++) for communicating with OpenAI (e.g., GPT-4o, GPT-4, GPT-3.5)

---

## 🚀 Features

- 💬 Maintains conversation history across prompts
- 🧠 Optional reset for starting fresh conversations (`reset_conversation`)
- ⚙️ Dynamically selectable OpenAI model via launch argument (`gpt-5-nano`, `gpt-5-mini`, `gpt-4o`, ` or e.g. gpt-3.5-turbo`, `gpt-4-1106-preview`, etc.)
- ✍️ Supports pre_prompt instructions (system message prepended to prompt)
- 📦 Fully implemented in C++ and ROS 2-native

---

## 🧪 Example Usage

### Launch the server using a launch file:

```bash
ros2 launch openai_server openai_server_launch.py \
  openai_api_key:=<your_openai_api_key> \
  openai_model:=gpt-5-nano
```

### Call the service via CLI:

```bash
ros2 service call /openai_ask openai_server_interfaces/srv/OpenaiServer \
"{prompt: 'What is ROS 2?', reset_conversation: false, pre_prompt: 'Please answer briefly and in English.'}"
```

---

## 📦 Dependencies

### ROS 2 packages

- `rclcpp`
- `std_msgs`
- `launch`, `launch_ros`
- `curl` (C++ HTTP client library)
- `nlohmann_json` (for JSON parsing)

### System packages (on Ubuntu):

```bash
sudo apt install libcurl4-openssl-dev nlohmann-json3-dev
```

---

## 🧩 Installation & Build

### Setup workspace

```bash
mkdir -p ~/ros2_openai_ws/src
cd ~/ros2_openai_ws/src
git clone <gitlab-url>  # clone this repository
cd ..
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
```

---

## 📁 `OpenaiServer.srv` structure

```srv
# Request:
string prompt             # Question or input for the model
bool reset_conversation   # true = start new conversation, false = continue history
string pre_prompt         # Optional system-level prompt before user message

---
# Response:
string response           # OpenAI's generated response
```

---

## ⚙️ Launch Parameters

| Parameter         | Description                                        | Default Value  |
|------------------|----------------------------------------------------|----------------|
| `openai_api_key` | Your OpenAI API key                                | (required)     |
| `openai_model`   | Model name like `gpt-4o`, `gpt-3.5-turbo`, etc.    | `gpt-4o`       |

---

## 💡 Tips

- Context is retained across prompts unless `reset_conversation: true` is set
- Use `reset_conversation: true` to begin a new thread
- Add `pre_prompt` for task-specific or behavioral guidance (e.g., language, style)

---

## 🔒 Security Note

- Do **not** hardcode your API key in source or launch files
- Use environment variables or `.env` configuration for safer deployments

---

## 🧑‍💻 License & Contributions

This project is licensed under the MIT License.  
Contributions, improvements, and pull requests are welcome!

---

## 📬 Contact

Developed by: **Sebastian Reitelshöfer with ChatCPT**  
For issues or feedback, please use the GitLab issue tracker.

---