import os
import glob

print("Searching for mydatabase.db in root workspace:")
for root, dirs, files in os.walk("E:\\Hydroagrix Ai\\Ai Dosing Unit"):
    for file in files:
        if file == "mydatabase.db":
            print("Found in root workspace:", os.path.join(root, file))

print("Searching in User directory:")
user_dir = "C:\\Users\\shriy"
# Only search 3 levels deep under C:\Users\shriy to avoid slow traversals
for root, dirs, files in os.walk(user_dir):
    depth = root[len(user_dir):].count(os.sep)
    if depth > 3:
        # Prune deep subdirectories
        dirs[:] = []
        continue
    for file in files:
        if file in ("mydatabase.db", "hydroponics.db"):
            print("Found in User directory:", os.path.join(root, file))
