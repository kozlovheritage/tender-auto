import smtplib
import json
import ssl

def test_smtp():
    # Путь к вашему исправленному конфигу
    config_path = "profiles/vitro/sender_config.json"
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            
        # Надежно достаём данные (на случай если где-то затесался лишний пробел в ключе)
        vitro = config.get("vitro") or config.get("vitro ") or {}
        
        email = (vitro.get("email") or vitro.get("email ")).strip()
        password = (vitro.get("password") or vitro.get("password ")).strip()
        host = (vitro.get("smtp_host") or vitro.get("smtp_host ")).strip()
        port = int(vitro.get("smtp_port") or vitro.get("smtp_port "))
        
        print(f"🔌 Тестируем подключение к {host}:{port} для {email}...")
        
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(email, password)
            
        print("✅ УСПЕХ! Связь с Gmail установлена, авторизация пройдена.")
        print("🚀 Настройки верны, можно запускать основную программу.")
        
    except FileNotFoundError:
        print(f"❌ Файл не найден по пути: {config_path}")
        print("Убедитесь, что вы запускаете скрипт из корневой папки проекта (там же, где лежит папка profiles).")
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка чтения JSON: {e}")
        print("Проверьте файл sender_config.json на наличие опечаток, лишних запятых или незакрытых кавычек.")
    except smtplib.SMTPAuthenticationError:
        print("❌ ОШИБКА АВТОРИЗАЦИИ (SMTPAuthenticationError)!")
        print("Gmail отклонил пароль. Убедитесь, что вы используете именно 16-значный 'Пароль приложения' (App Password), сгенерированный в Google, а не ваш основной пароль от почты.")
    except Exception as e:
        print(f"❌ Непредвиденная ошибка сети или конфига: {e}")

if __name__ == "__main__":
    test_smtp()