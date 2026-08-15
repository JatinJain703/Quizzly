from PIL import Image

def process_logo():
    img = Image.open("d:/Quizzly/frontend/public/logo.png").convert("RGBA")
    data = img.getdata()
    new_data = []
    
    for item in data:
        # If the pixel is mostly white (or light gray), make it fully transparent
        if item[0] > 200 and item[1] > 200 and item[2] > 200:
            new_data.append((255, 255, 255, 0))
        else:
            # Otherwise, if it has any opacity, make it solid black
            if item[3] > 0:
                new_data.append((0, 0, 0, item[3]))
            else:
                new_data.append(item)

    img.putdata(new_data)
    img.save("d:/Quizzly/frontend/public/logo_black.png")
    print("Logo processed successfully!")

if __name__ == "__main__":
    process_logo()
