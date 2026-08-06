cmake_minimum_required(VERSION 3.8)
project(pepper_moveit2_config)

find_package(ament_cmake REQUIRED)

install(DIRECTORY config launch rviz resource
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
