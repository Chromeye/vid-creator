import base64


def main():

    with open('./ref_girl_2_9-16.jpg', 'rb') as img_file:
        img_data = img_file.read()
        img_base64 = base64.b64encode(img_data).decode('utf-8')
        print(img_base64)


if __name__ == "__main__":
    main()
