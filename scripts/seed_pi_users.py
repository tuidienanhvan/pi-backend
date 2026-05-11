import asyncio
from datetime import datetime, timedelta, timezone
from typing import cast

from sqlalchemy import select
from app.core.db import AsyncSessionLocal
from app.shared.auth.service import AuthService
from app.shared.license.models import License, LicenseTier

# Danh sách người dùng mẫu với các Tier khác nhau
USERS = [
    {"email": "free@pi.com", "password": "password123", "name": "Pi Free User", "tier": "free"},
    {"email": "pro@pi.com", "password": "password123", "name": "Pi Pro User", "tier": "pro"},
    {"email": "max@pi.com", "password": "password123", "name": "Pi Max User", "tier": "max"},
]

# HIỆN TẠI: Hệ thống đã hợp nhất, chỉ cần license cho core plugin pi-api.
PLUGINS = ["pi-api"]

async def main() -> None:
    async with AsyncSessionLocal() as db:
        auth_svc = AuthService(db)
        
        print("STARTING UNIFIED SEEDING...")
        
        for u in USERS:
            print(f"\nProcessing {u['email']}...")
            
            # 1. Khởi tạo hoặc cập nhật User
            user = await auth_svc.get_by_email(u['email'])
            if not user:
                user = await auth_svc.create_user(
                    email=u['email'],
                    password=u['password'],
                    name=u['name'],
                    is_admin=False
                )
                user.is_verified = True
                print(f"  [OK] Created user: {u['email']}")
            else:
                # Cập nhật thông tin nếu user đã tồn tại
                user.name = u['name']
                user.password_hash = auth_svc.hash_password(u['password'])
                print(f"  [UPDATE] User exists, synced info for: {u['email']}")

            # 2. Cấp License cho Unified Plugin (pi-api)
            for plugin in PLUGINS:
                # Kiểm tra license đã tồn tại chưa
                existing_lic = (await db.execute(
                    select(License).where(License.email == u['email'], License.plugin == plugin)
                )).scalar_one_or_none()
                
                if not existing_lic:
                    # Tạo license mới cho kiến trúc hợp nhất
                    lic = License.new(
                        plugin=plugin,
                        email=u['email'],
                        tier=cast(LicenseTier, u['tier']),
                        max_sites=10 if u['tier'] == 'max' else (3 if u['tier'] == 'pro' else 1),
                        customer_name=u['name']
                    )
                    lic.expires_at = datetime.now(timezone.utc) + timedelta(days=365)
                    db.add(lic)
                    print(f"  [OK] Created {u['tier']} UNIFIED license for {plugin}: {lic.key}")
                else:
                    # Đồng bộ Tier nếu đã có license
                    existing_lic.tier = cast(LicenseTier, u['tier'])
                    print(f"  [UPDATE] Updated existing {plugin} license to tier: {u['tier']}")

        await db.commit()
        print("\n" + "========================================")
        print("UNIFIED SEEDING COMPLETED SUCCESSFULLY")
        print("========================================")

if __name__ == "__main__":
    asyncio.run(main())
