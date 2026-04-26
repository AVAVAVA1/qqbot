import os


# 启动napcat
def run_napcat():
    status = os.system("D:\\NapCat\\NapCat.Shell\\launcher_oguri.bat")
    print(f"BAT执行状态码：{status}")


if __name__ == "__main__":
    run_napcat()
