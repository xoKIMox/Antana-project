import subprocess
import os

print("CWD:", os.getcwd())

cmd1 = ["python", "manage.py", "makemigrations", "accounts"]
print(f"Running: {' '.join(cmd1)}")
res = subprocess.run(cmd1, capture_output=True, text=True)
print("STDOUT:", res.stdout)
print("STDERR:", res.stderr)

cmd2 = ["python", "manage.py", "migrate"]
print(f"Running: {' '.join(cmd2)}")
res2 = subprocess.run(cmd2, capture_output=True, text=True)
print("MIGRATE STDOUT:", res2.stdout)
print("MIGRATE STDERR:", res2.stderr)
