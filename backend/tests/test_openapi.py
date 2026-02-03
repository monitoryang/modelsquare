import requests

API_KEY = "msk_Naqgc8bZS6vTYUkcqwWO-8e7H84RVt4FkviwOwjworE"
MODEL_ID = "f57bef24-7751-4fc6-bed6-51cec757bda4"
API_URL = "http://localhost:8020/api/v1/openapi/models/{}/detect".format(MODEL_ID)

# 准备图片文件
with open("/home/jouav/图片/松材线虫.png", "rb") as f:
    files = {"image": ("image.png", f, "image/png")}
    data = {
        "conf_threshold": 0.25,
        "iou_threshold": 0.45
    }
    params = {"api_key": API_KEY}
    
    response = requests.post(API_URL, files=files, data=data, params=params)
    
if response.status_code == 200:
    result = response.json()
    print(f"检测到 {len(result['boxes'])} 个目标")
    for i, (box, score, class_name) in enumerate(zip(
        result['boxes'], result['scores'], result['class_names']
    )):
        print(f"  {i+1}. {class_name}: {score*100:.1f}% at {box}")
else:
    print(f"Error: {response.status_code}")
    print(response.text)