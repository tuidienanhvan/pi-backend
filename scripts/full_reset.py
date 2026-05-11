import asyncio
import subprocess
import sys
import os
from pathlib import Path

import io

# Thêm thư mục gốc vào path để import được app
ROOT_DIR = Path(__file__).parent.parent
sys.path.append(str(ROOT_DIR))

# Force UTF-8 for Windows console
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

async def run_command(cmd: str):
    print(f"\n> Executing: {cmd}")
    # Đảm bảo dùng đúng python executable của venv nếu đang ở trong venv
    python_exe = sys.executable
    
    # Nếu lệnh bắt đầu bằng 'python', thay bằng python_exe hiện tại
    if cmd.startswith("python "):
        cmd = cmd.replace("python ", f'"{python_exe}" ', 1)

    process = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(ROOT_DIR),
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONPATH": "."}
    )
    stdout, stderr = await process.communicate()
    
    if stdout:
        print(stdout.decode(errors="replace"))
    if stderr:
        print(stderr.decode(errors="replace"), file=sys.stderr)
        
    if process.returncode != 0:
        return False
    return True

async def main():
    print("==================================================")
    print("   PI BACKEND: FULL SYSTEM RESET & RE-SEED")
    print("==================================================")
    
    # 1. Reset Database via Alembic
    print("\n[1/7] Resetting Database Schema...")
    if not await run_command("python -m alembic downgrade base"): 
        print("❌ Failed to downgrade database.")
        return
    if not await run_command("python -m alembic upgrade head"):
        print("❌ Failed to upgrade database.")
        return

    # 2. Run Seeder Scripts
    print("\n[2/7] Creating Admin User (admin@piwebagency.com / SuperSecret!)...")
    admin_cmd = 'python -m scripts.create_admin --email admin@piwebagency.com --password "SuperSecret!" --name "Pi Admin"'
    if not await run_command(admin_cmd): return

    print("\n[3/7] Seeding AI Providers & Packages...")
    if not await run_command("python -m scripts.seed_ai_providers"): return

    print("\n[4/7] Seeding API Key Pool (Dummy Keys)...")
    if not await run_command("python -m scripts.seed_pool_keys"): return

    print("\n[5/7] Seeding Sample Users & Licenses...")
    if not await run_command("python -m scripts.seed_pi_users"): return

    print("\n[6/7] Allocating Pro Licenses...")
    if not await run_command("python -m scripts.seed_pro_licenses"): return

    print("\n[7/7] Seeding Demo Tenants...")
    if not await run_command("python -m scripts.seed_test_tenants"): return

    print("\n" + "="*50)
    print("✅ SUCCESS: FULL RESET & SEED COMPLETED")
    print("==================================================")
    print("Login Email:    admin@piwebagency.com")
    print("Login Password: SuperSecret!")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(main())
