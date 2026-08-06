# Pepper Autonomous Navigation Documentation

## Architecture

```
/laser -> pepper_laser_filter -> /scan_clean
/camera/depth/image_raw -> depthimage_to_laserscan -> /depth_scan
/camera/front/image_raw -> VLM -> /smolvlm/output

Mapping:
  /scan_clean -> slam_toolbox -> /map

Navigation:
  saved map + /scan_clean -> AMCL + Nav2 -> /cmd_vel

Semantic waypoint:
  current map pose + latest VLM text -> pepper_waypoints.yaml
  place name -> NavigateToPose
```

## Why `/scan_clean` is required

Pepper's raw `/laser` scan can have invalid ranges and inconsistent LaserScan geometry. The filter removes invalid data and recomputes `angle_max` from the actual beam count.

## Workflow

1. Build the package.
2. Copy `pepper_prepare_posture.py` to Pepper.
3. Run mapping launch.
4. Save the map.
5. Run autonomous navigation launch.
6. Set the initial pose in RViz.
7. Send Nav2 goals.
8. Save semantic waypoints.
9. Navigate to named places.

## Depth camera

Use `/depth_scan` for local obstacle awareness, not as the main mapping source.
