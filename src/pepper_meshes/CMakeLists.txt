cmake_minimum_required(VERSION 3.10)
project(pepper_meshes)

find_package(ament_cmake REQUIRED)

install(
  DIRECTORY meshes/
  DESTINATION share/${PROJECT_NAME}/meshes
)

ament_package()
