import shutil
from pathlib import Path

def clean_results_folder():
    results_path = Path("results")

    if not results_path.exists():
        print("📁 Папка 'results' не существует — нечего чистить.")
        return

    for item in results_path.iterdir():
        try:
            if item.is_file() or item.is_symlink():
                item.unlink()
                print(f"🗑️ Удалён файл: {item}")
            elif item.is_dir():
                shutil.rmtree(item)
                print(f"🧹 Удалена папка: {item}")
        except Exception as e:
            print(f"⚠️ Ошибка при удалении {item}: {e}")

    print("✅ Папка 'results' очищена.")

if __name__ == "__main__":
    clean_results_folder()
