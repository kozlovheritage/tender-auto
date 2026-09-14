import os, sys, shutil, io, re, subprocess

profile = 'default'
if len(sys.argv) > 1 and sys.argv[1] == '--profile' and len(sys.argv) > 2:
    profile = sys.argv[2]

profile_dir = os.path.join('profiles', profile)
if not os.path.exists(profile_dir):
    print(f'❌ Профиль {profile} не найден в profiles/'); sys.exit(1)

print(f'📦 Сборка с профилем: {profile}')

# 1. Копируем конфиги из профиля в корень (для сборки)
for f in ['settings.toml', 'sampler_config.txt', 'brands_extra.txt']:
    src = os.path.join(profile_dir, f)
    if os.path.exists(src):
        shutil.copy2(src, f)
        print(f'  ✓ {f} из профиля')

for f in ['sender_config.json', 'rfq_template.txt']:
    src = os.path.join(profile_dir, f)
    if os.path.exists(src):
        dst = ('templates' if f == 'rfq_template.txt'
           else 'config' if f == 'sender_config.json'
           else '.')
        shutil.copy2(src, os.path.join(dst, f))
        print(f'  ✓ {f} из профиля')

# 2. Запускаем оригинальный make_product.py
subprocess.run([sys.executable, 'make_product.py'], check=True)

# 3. Переименовываем итоговую папку
src = os.path.join('dist', 'TenderAuto')
dst = os.path.join('dist', f'TenderAuto_{profile}')
if os.path.exists(dst):
    shutil.rmtree(dst)
os.rename(src, dst)
print(f'✅ Продуктовая папка: {dst}')