cmake_minimum_required(VERSION 3.8)
project(pepper_moveit2_bridge)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)
find_package(trajectory_msgs REQUIRED)
find_package(moveit_ros_planning_interface REQUIRED)

add_executable(pepper_named_target_planner src/pepper_named_target_planner.cpp)
ament_target_dependencies(
  pepper_named_target_planner
  rclcpp
  std_msgs
  trajectory_msgs
  moveit_ros_planning_interface
)

target_compile_features(pepper_named_target_planner PUBLIC cxx_std_17)

install(TARGETS
  pepper_named_target_planner
  DESTINATION lib/${PROJECT_NAME}
)

install(PROGRAMS
  scripts/pepper_trajectory_executor.py
  scripts/pepper_trajectory_action_saver.py
  scripts/pepper_publish_neutral_pose.py
  scripts/pepper_direct_named_pose_executor.py
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY
  launch
  config
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
