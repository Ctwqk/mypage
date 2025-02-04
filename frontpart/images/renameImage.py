import os

# 设置文件夹路径
folder_path = "./"

# 获取文件夹中所有文件
file_list = os.listdir(folder_path)

# 过滤出所有图片文件（以.jpg结尾）
images = [f for f in file_list if f.lower().endswith(".jpg")]

# 按名字排序，保证顺序一致
images.sort()

# 重命名文件
for index, image in enumerate(images, start=1):
    old_path = os.path.join(folder_path, image)           # 原始文件路径
    new_name = f"{index}.jpg"                            # 新文件名
    new_path = os.path.join(folder_path, new_name)       # 新文件路径
    os.rename(old_path, new_path)
    print(f"Renamed: {image} -> {new_name}")

print("所有文件重命名完成！")
