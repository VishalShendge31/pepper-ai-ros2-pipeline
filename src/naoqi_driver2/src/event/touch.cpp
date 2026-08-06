/*
 * Copyright 2015 Aldebaran
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
*/

#include <iostream>
#include <vector>
#include <exception>
#include <stdexcept>

#include <boost/make_shared.hpp>
#include <boost/bind.hpp>
#include <boost/chrono.hpp>
#include <boost/thread.hpp>

#include <rclcpp/rclcpp.hpp>

#include <qi/anyobject.hpp>
#include <qi/anyvalue.hpp>
#include <qi/type/typeinterface.hpp>

#include <naoqi_driver/recorder/globalrecorder.hpp>
#include <naoqi_driver/message_actions.h>

#include "touch.hpp"

namespace naoqi
{

template<class T>
TouchEventRegister<T>::TouchEventRegister()
{
}

template<class T>
TouchEventRegister<T>::TouchEventRegister(
    const std::string& name,
    const std::vector<std::string> keys,
    const float& frequency,
    const qi::SessionPtr& session )
  : name_(name),
    keys_(keys),
    session_(session),
    p_memory_(session->service("ALMemory").value()),
    isStarted_(false),
    isPublishing_(false),
    isRecording_(false),
    isDumping_(false),
    use_polling_(false)
{
  publisher_ = boost::make_shared<publisher::BasicPublisher<T>>(name_);
  converter_ = boost::make_shared<converter::TouchEventConverter<T>>(name_, frequency, session_);

  converter_->registerCallback(
      message_actions::PUBLISH,
      boost::bind(&publisher::BasicPublisher<T>::publish, publisher_, boost::placeholders::_1));
}

template<class T>
TouchEventRegister<T>::~TouchEventRegister()
{
  stopProcess();
}

template<class T>
void TouchEventRegister<T>::resetPublisher(rclcpp::Node* node)
{
  publisher_->reset(node);
}

template<class T>
void TouchEventRegister<T>::resetRecorder(boost::shared_ptr<naoqi::recorder::GlobalRecorder> /*gr*/)
{
}

template<class T>
void TouchEventRegister<T>::startProcess()
{
  boost::mutex::scoped_lock lock(mutex_);

  if (isStarted_)
  {
    return;
  }

  std::size_t success_count = 0;
  use_polling_ = false;
  subscriptions_.clear();
  poll_failures_.clear();
  disabled_keys_.clear();
  last_values_.clear();

  for (const auto& key : keys_)
  {
    try
    {
      qi::AnyObject subscriber = p_memory_.call<qi::AnyObject>("subscriber", key);

      qi::SignalLink link =
          subscriber.connect("signal", [this, key](const qi::AnyValue& v)
          {
            this->touchCallback(key, v);
          }).value();

      subscriptions_.emplace_back(subscriber, link);
      ++success_count;
    }
    catch (const std::exception&)
    {
      // Fallback to polling if event subscription is not supported for this key/runtime.
    }
    catch (...)
    {
      // Fallback to polling if event subscription is not supported for this key/runtime.
    }
  }

  if (success_count == 0)
  {
    use_polling_ = true;

    for (const auto& key : keys_)
    {
      poll_failures_[key] = 0;
      disabled_keys_[key] = false;

      try
      {
        qi::AnyValue raw = p_memory_.call<qi::AnyValue>("getData", key);

        if (raw.kind() == qi::TypeKind_Float)
        {
          last_values_[key] = raw.toFloat();
        }
        else if (raw.kind() == qi::TypeKind_Int)
        {
          last_values_[key] = static_cast<float>(raw.toInt());
        }
        else
        {
          last_values_[key] = 0.0f;
        }
      }
      catch (...)
      {
        last_values_[key] = 0.0f;
      }
    }
  }

  isStarted_ = true;

  if (use_polling_)
  {
    polling_thread_ = boost::thread([this]()
    {
      this->pollLoop();
    });
  }
}

template<class T>
void TouchEventRegister<T>::stopProcess()
{
  bool should_join = false;

  {
    boost::mutex::scoped_lock lock(mutex_);

    if (!isStarted_)
    {
      return;
    }

    isStarted_ = false;

    if (!subscriptions_.empty())
    {
      for (const auto& subscription : subscriptions_)
      {
        try
        {
          subscription.subscriber.disconnect(subscription.link).value();
        }
        catch (const std::exception&)
        {
        }
        catch (...)
        {
        }
      }

      subscriptions_.clear();
    }

    should_join = use_polling_;
    use_polling_ = false;
  }

  if (should_join && polling_thread_.joinable())
  {
    polling_thread_.join();
  }
}

template<class T>
void TouchEventRegister<T>::writeDump(const rclcpp::Time& /*time*/)
{
}

template<class T>
void TouchEventRegister<T>::setBufferDuration(float /*duration*/)
{
}

template<class T>
void TouchEventRegister<T>::isRecording(bool state)
{
  boost::mutex::scoped_lock rec_lock(mutex_);
  isRecording_ = state;
}

template<class T>
void TouchEventRegister<T>::isPublishing(bool state)
{
  boost::mutex::scoped_lock pub_lock(mutex_);
  isPublishing_ = state;
}

template<class T>
void TouchEventRegister<T>::isDumping(bool state)
{
  boost::mutex::scoped_lock dump_lock(mutex_);
  isDumping_ = state;
}

template<class T>
void TouchEventRegister<T>::registerCallback()
{
}

template<class T>
void TouchEventRegister<T>::unregisterCallback()
{
}

template<class T>
void TouchEventRegister<T>::pollLoop()
{
  while (true)
  {
    bool running = false;
    bool publishing = false;
    bool has_subscribers = false;

    {
      boost::mutex::scoped_lock lock(mutex_);
      running = isStarted_ && use_polling_;
      publishing = isPublishing_;
      has_subscribers = publisher_->isSubscribed();
    }

    if (!running)
    {
      break;
    }

    for (const auto& key : keys_)
    {
      {
        boost::mutex::scoped_lock lock(mutex_);
        if (disabled_keys_[key])
        {
          continue;
        }
      }

      try
      {
        qi::AnyValue raw = p_memory_.call<qi::AnyValue>("getData", key);

        float value = 0.0f;

        if (raw.kind() == qi::TypeKind_Float)
        {
          value = raw.toFloat();
        }
        else if (raw.kind() == qi::TypeKind_Int)
        {
          value = static_cast<float>(raw.toInt());
        }
        else
        {
          throw std::runtime_error("unsupported ALMemory type");
        }

        bool changed = false;
        {
          boost::mutex::scoped_lock lock(mutex_);
          float prev = last_values_[key];
          if (value != prev)
          {
            last_values_[key] = value;
            poll_failures_[key] = 0;
            changed = true;
          }
          else
          {
            poll_failures_[key] = 0;
          }
        }

        if (changed)
        {
          bool state = value > 0.5f;

          T msg = T();
          touchCallbackMessage(key, state, msg);

          std::vector<message_actions::MessageAction> actions;

          if (publishing && has_subscribers)
          {
            actions.push_back(message_actions::PUBLISH);
          }

          if (!actions.empty())
          {
            converter_->callAll(actions, msg);
          }
        }
      }
      catch (const std::exception& e)
      {
        bool disable_now = false;
        int failures = 0;

        {
          boost::mutex::scoped_lock lock(mutex_);
          failures = ++poll_failures_[key];
          if (failures >= 5)
          {
            disabled_keys_[key] = true;
            disable_now = true;
          }
        }

        if (disable_now)
        {
          std::cerr << "[touch] disabling key " << key
                    << " after repeated polling failures: "
                    << e.what() << std::endl;
        }
      }
      catch (...)
      {
        bool disable_now = false;

        {
          boost::mutex::scoped_lock lock(mutex_);
          const int failures = ++poll_failures_[key];
          if (failures >= 5)
          {
            disabled_keys_[key] = true;
            disable_now = true;
          }
        }

        if (disable_now)
        {
          std::cerr << "[touch] disabling key " << key
                    << " after repeated polling failures: unknown exception"
                    << std::endl;
        }
      }
    }

    boost::this_thread::sleep_for(boost::chrono::milliseconds(50));
  }
}

template<class T>
void TouchEventRegister<T>::touchCallback(const std::string &key, const qi::AnyValue& value)
{
  T msg = T();
  bool state = value.toFloat() > 0.5f;

  touchCallbackMessage(key, state, msg);

  std::vector<message_actions::MessageAction> actions;
  boost::mutex::scoped_lock callback_lock(mutex_);

  if (isStarted_)
  {
    if (isPublishing_ && publisher_->isSubscribed())
    {
      actions.push_back(message_actions::PUBLISH);
    }

    if (!actions.empty())
    {
      converter_->callAll(actions, msg);
    }
  }
}

template<class T>
void TouchEventRegister<T>::touchCallbackMessage(
    const std::string &key,
    bool &state,
    naoqi_bridge_msgs::msg::Bumper &msg)
{
  int i = 0;
  for (std::vector<std::string>::const_iterator it = keys_.begin(); it != keys_.end(); ++it, ++i)
  {
    if (key == *it)
    {
      msg.bumper = i;
      msg.state = state
          ? naoqi_bridge_msgs::msg::Bumper::STATE_PRESSED
          : naoqi_bridge_msgs::msg::Bumper::STATE_RELEASED;
      break;
    }
  }
}

template<class T>
void TouchEventRegister<T>::touchCallbackMessage(
    const std::string &key,
    bool &state,
    naoqi_bridge_msgs::msg::HandTouch &msg)
{
  int i = 0;
  for (std::vector<std::string>::const_iterator it = keys_.begin(); it != keys_.end(); ++it, ++i)
  {
    if (key == *it)
    {
      msg.hand = i;
      msg.state = state
          ? naoqi_bridge_msgs::msg::HandTouch::STATE_PRESSED
          : naoqi_bridge_msgs::msg::HandTouch::STATE_RELEASED;
      break;
    }
  }
}

template<class T>
void TouchEventRegister<T>::touchCallbackMessage(
    const std::string &key,
    bool &state,
    naoqi_bridge_msgs::msg::HeadTouch &msg)
{
  int i = 0;
  for (std::vector<std::string>::const_iterator it = keys_.begin(); it != keys_.end(); ++it, ++i)
  {
    if (key == *it)
    {
      msg.button = i;
      msg.state = state
          ? naoqi_bridge_msgs::msg::HeadTouch::STATE_PRESSED
          : naoqi_bridge_msgs::msg::HeadTouch::STATE_RELEASED;
      break;
    }
  }
}

template class TouchEventRegister<naoqi_bridge_msgs::msg::Bumper>;
template class TouchEventRegister<naoqi_bridge_msgs::msg::HandTouch>;
template class TouchEventRegister<naoqi_bridge_msgs::msg::HeadTouch>;

} // namespace naoqi
