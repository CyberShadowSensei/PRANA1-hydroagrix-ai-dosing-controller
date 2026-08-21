import subprocess
import os

cwd = r"e:\Hydroagrix Ai\Ai Dosing Unit\backend"
try:
    result = subprocess.run(
        ["python", "-m", "pytest", "-v", "--tb=short"], 
        cwd=cwd, 
        capture_output=True, 
        text=True
    )
    with open(os.path.join(cwd, "test_output.txt"), "w") as f:
        f.write("STDOUT:\n")
        f.write(result.stdout)
        f.write("\nSTDERR:\n")
        f.write(result.stderr)
        f.write("\nRETURN CODE: " + str(result.returncode))
except Exception as e:
    with open(os.path.join(cwd, "test_output.txt"), "w") as f:
        f.write(str(e))
