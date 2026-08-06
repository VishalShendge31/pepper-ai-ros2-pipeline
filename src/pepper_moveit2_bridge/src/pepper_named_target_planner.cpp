#include <memory>
#include <string>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/string.hpp>
#include <trajectory_msgs/msg/joint_trajectory.hpp>
#include <moveit/move_group_interface/move_group_interface.h>
#include <moveit/planning_interface/planning_interface.h>
#include <moveit_msgs/msg/move_it_error_codes.hpp>

class PepperNamedTargetPlanner
{
public:
  explicit PepperNamedTargetPlanner(const rclcpp::Node::SharedPtr & node)
  : node_(node)
  {
    node_->declare_parameter<std::string>("planning_group", "right_arm");
    node_->declare_parameter<std::string>("goal_topic", "/pepper/moveit_named_goal");
    node_->declare_parameter<std::string>("trajectory_topic", "/pepper_moveit/planned_trajectory");
    node_->declare_parameter<double>("planning_time", 5.0);
    node_->declare_parameter<double>("max_velocity_scaling", 0.20);
    node_->declare_parameter<double>("max_acceleration_scaling", 0.20);
    node_->declare_parameter<bool>("execute_with_moveit", false);
    node_->declare_parameter<bool>("publish_planned_trajectory", true);

    planning_group_ = node_->get_parameter("planning_group").as_string();
    goal_topic_ = node_->get_parameter("goal_topic").as_string();
    trajectory_topic_ = node_->get_parameter("trajectory_topic").as_string();
    planning_time_ = node_->get_parameter("planning_time").as_double();
    max_velocity_scaling_ = node_->get_parameter("max_velocity_scaling").as_double();
    max_acceleration_scaling_ = node_->get_parameter("max_acceleration_scaling").as_double();
    execute_with_moveit_ = node_->get_parameter("execute_with_moveit").as_bool();
    publish_planned_trajectory_ = node_->get_parameter("publish_planned_trajectory").as_bool();

    RCLCPP_INFO(node_->get_logger(), "Creating MoveGroupInterface for planning group: %s", planning_group_.c_str());

    move_group_ = std::make_unique<moveit::planning_interface::MoveGroupInterface>(node_, planning_group_);
    move_group_->setPlanningTime(planning_time_);
    move_group_->setMaxVelocityScalingFactor(max_velocity_scaling_);
    move_group_->setMaxAccelerationScalingFactor(max_acceleration_scaling_);

    trajectory_pub_ = node_->create_publisher<trajectory_msgs::msg::JointTrajectory>(trajectory_topic_, 10);

    goal_sub_ = node_->create_subscription<std_msgs::msg::String>(
      goal_topic_,
      10,
      std::bind(&PepperNamedTargetPlanner::goalCallback, this, std::placeholders::_1));

    RCLCPP_INFO(node_->get_logger(), "Listening for named MoveIt targets on: %s", goal_topic_.c_str());
    RCLCPP_INFO(node_->get_logger(), "Publishing planned trajectories on: %s", trajectory_topic_.c_str());
    RCLCPP_INFO(node_->get_logger(), "execute_with_moveit: %s", execute_with_moveit_ ? "true" : "false");
  }

private:
  void goalCallback(const std_msgs::msg::String::SharedPtr msg)
  {
    const std::string target_name = trim(msg->data);

    if (target_name.empty()) {
      RCLCPP_WARN(node_->get_logger(), "Ignored empty MoveIt target name.");
      return;
    }

    RCLCPP_INFO(node_->get_logger(), "Planning named target '%s' for group '%s'", target_name.c_str(), planning_group_.c_str());

    move_group_->setStartStateToCurrentState();

    const bool target_set = move_group_->setNamedTarget(target_name);
    if (!target_set) {
      RCLCPP_ERROR(
        node_->get_logger(),
        "Named target '%s' is not known for planning group '%s'. Check the SRDF named states.",
        target_name.c_str(),
        planning_group_.c_str());
      return;
    }

    moveit::planning_interface::MoveGroupInterface::Plan plan;
    const auto result = move_group_->plan(plan);

    if (result != moveit::core::MoveItErrorCode::SUCCESS) {
      RCLCPP_ERROR(node_->get_logger(), "MoveIt planning failed for target '%s'.", target_name.c_str());
      return;
    }

    if (plan.trajectory_.joint_trajectory.points.empty()) {
      RCLCPP_ERROR(node_->get_logger(), "MoveIt returned an empty trajectory for target '%s'.", target_name.c_str());
      return;
    }

    RCLCPP_INFO(
      node_->get_logger(),
      "Plan succeeded. Joint count: %zu, point count: %zu",
      plan.trajectory_.joint_trajectory.joint_names.size(),
      plan.trajectory_.joint_trajectory.points.size());

    if (publish_planned_trajectory_) {
      trajectory_pub_->publish(plan.trajectory_.joint_trajectory);
      RCLCPP_INFO(node_->get_logger(), "Published planned trajectory for Pepper bridge execution.");
    }

    if (execute_with_moveit_) {
      RCLCPP_WARN(node_->get_logger(), "Executing through MoveIt. Use only if a valid ros2_control controller exists.");
      const auto exec_result = move_group_->execute(plan);
      if (exec_result != moveit::core::MoveItErrorCode::SUCCESS) {
        RCLCPP_ERROR(node_->get_logger(), "MoveIt execution failed.");
      }
    }
  }

  static std::string trim(const std::string & input)
  {
    const auto first = input.find_first_not_of(" \t\n\r");
    if (first == std::string::npos) {
      return "";
    }
    const auto last = input.find_last_not_of(" \t\n\r");
    return input.substr(first, last - first + 1);
  }

  rclcpp::Node::SharedPtr node_;
  std::unique_ptr<moveit::planning_interface::MoveGroupInterface> move_group_;

  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr goal_sub_;
  rclcpp::Publisher<trajectory_msgs::msg::JointTrajectory>::SharedPtr trajectory_pub_;

  std::string planning_group_;
  std::string goal_topic_;
  std::string trajectory_topic_;
  double planning_time_;
  double max_velocity_scaling_;
  double max_acceleration_scaling_;
  bool execute_with_moveit_;
  bool publish_planned_trajectory_;
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);

  auto node = rclcpp::Node::make_shared("pepper_named_target_planner");

  auto planner = std::make_shared<PepperNamedTargetPlanner>(node);

  rclcpp::executors::MultiThreadedExecutor executor;
  executor.add_node(node);
  executor.spin();

  rclcpp::shutdown();
  return 0;
}
