import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# persistent cache between test runs keeps numba compile times out of the test loop
os.environ.setdefault("ATTRACTR_HOME", os.path.join(os.environ.get("TMPDIR", "/tmp"), "attractr_test_home"))
