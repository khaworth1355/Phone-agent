
with open("C:/Users/khawo/PycharmProjects/Phone-agent/app.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

print(f"Total lines in file: {len(lines)}")
print(f"
Line 498 (should no longer mention QuickBooks):")
print(f"{498}: {lines[497].rstrip()}")
print(f"
Line 628 (should no longer mention QuickBooks):")
print(f"{628}: {lines[627].rstrip()}")
print(f"
Line 980 (should no longer mention QuickBooks):")
print(f"{980}: {lines[979].rstrip()}")
print(f"
Line 1109 (should no longer mention QuickBooks):")
print(f"{1109}: {lines[1108].rstrip()}")

# Check that routes are removed
print("

Searching for removed routes:")
content = "".join(lines)
if '@app.route("/qb-connect")' in content:
    print("ERROR: /qb-connect route still exists!")
else:
    print("OK /qb-connect route removed")
    
if '@app.route("/qb-callback")' in content:
    print("ERROR: /qb-callback route still exists!")
else:
    print("OK /qb-callback route removed")
    
if '@app.route("/qb-status")' in content:
    print("ERROR: /qb-status route still exists!")
else:
    print("OK /qb-status route removed")
