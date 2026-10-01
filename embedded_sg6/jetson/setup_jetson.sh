#!/usr/bin/env bash
# SG-6: one-shot Jetson Orin Nano 8GB survey and setup.
#
# Run it once per device, then paste what it prints into embedded_sg6/README.md.
# Most of it only REPORTS -- it deliberately does not install or change anything
# without you deciding to, because an undocumented environment change on the
# shared target device is how a whole team loses an afternoon.
#
# STATUS: scaffolding, never executed on hardware. Read every line before running.

set -euo pipefail

echo "=============================================================="
echo " 1. JetPack / L4T version   -- PIN THIS AND WRITE IT DOWN (R7)"
echo "=============================================================="
cat /etc/nv_tegra_release 2>/dev/null || echo "  not a Tegra device"
dpkg -l 'nvidia-jetpack*' 2>/dev/null | tail -2 || true

echo
echo "=============================================================="
echo " 2. What JetPack already provides -- do NOT pip install these"
echo "=============================================================="
python3 -c "import cv2; print('  opencv  ', cv2.__version__, '| cuda devices:', cv2.cuda.getCudaEnabledDeviceCount())" 2>/dev/null || echo "  opencv   MISSING"
python3 -c "import numpy; print('  numpy   ', numpy.__version__)" 2>/dev/null || echo "  numpy    MISSING"
python3 -c "import tensorrt; print('  tensorrt', tensorrt.__version__)" 2>/dev/null || echo "  tensorrt MISSING"
python3 -c "import cv2; print('  gstreamer in opencv:', 'GStreamer:                   YES' in cv2.getBuildInformation())" 2>/dev/null || true

echo
echo "=============================================================="
echo " 3. Cameras"
echo "=============================================================="
ls -l /dev/video* 2>/dev/null || echo "  no /dev/video* -- is the camera attached?"
if command -v v4l2-ctl >/dev/null 2>&1; then
  v4l2-ctl --list-formats-ext -d /dev/video0 2>/dev/null | head -40
else
  echo "  v4l2-ctl not installed:  sudo apt install v4l-utils"
fi

echo
echo "=============================================================="
echo " 4. Clocks -- DO THIS BEFORE ANY FPS MEASUREMENT"
echo "=============================================================="
echo "  sudo nvpmodel -m 0      # MAXN power mode"
echo "  sudo jetson_clocks      # pin clocks to maximum"
echo
echo "  A profiling run taken without these is NOT comparable to one taken with"
echo "  them. Record which mode every number in your report came from."

echo
echo "=============================================================="
echo " 5. Python dependencies (the short list)"
echo "=============================================================="
echo "  pip3 install -r embedded_sg6/requirements-jetson.txt"

echo
echo "=============================================================="
echo " 6. Smoke-test capture BEFORE wiring the pipeline to it (R7)"
echo "=============================================================="
cat <<'SMOKE'
  python3 - <<'PY'
  import itertools, sys
  sys.path.insert(0, ".")
  from embedded_sg6.src.capture_jetson import JetsonCameraSource
  n = sum(1 for _ in itertools.islice(JetsonCameraSource(camera="usb"), 60))
  print(f"captured {n} frames")
  PY
SMOKE

echo
echo "=============================================================="
echo " 7. Then, and only then, the pipeline"
echo "=============================================================="
echo "  python3 integration/run_pipeline.py --source mock     # no camera needed"
echo "  python3 integration/run_pipeline.py --source 0        # real camera"
echo "  python3 embedded_sg6/profiling/profile_pipeline.py --source 0 --limit 900"
echo "  tegrastats --interval 1000 --logfile tegrastats.log   # run alongside"
