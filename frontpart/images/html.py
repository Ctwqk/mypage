import base64
import os

# Function to convert a file (image or GIF) to base64 string
def convert_to_base64(file_path):
    with open(file_path, "rb") as file:
        encoded_string = base64.b64encode(file.read()).decode('utf-8')
    return encoded_string

# Paths to your image and GIF files
image_folder_path = './test_result'  # Replace with your image folder path
image_unittest_folder_path = './art_result'

# Convert all images in the folder to base64
image_filenames = sorted([f for f in os.listdir(image_folder_path) if f.endswith('.jpg')])
image_unittest_filenames=sorted([f for f in os.listdir(image_unittest_folder_path) if f.endswith('.jpg')])

image_base64_list = []
for image_filename in image_filenames:
    image_path = os.path.join(image_folder_path, image_filename)
    image_base64 = convert_to_base64(image_path)
    image_base64_list.append((image_filename, image_base64))
    
image_unittest_base64_list=[]
for image_filename in image_unittest_filenames:
    image_path = os.path.join(image_unittest_folder_path, image_filename)
    image_base64 = convert_to_base64(image_path)
    image_unittest_base64_list.append((image_filename, image_base64))


# Generate the HTML content with base64-encoded images and GIFs
html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ray Trace</title>
</head>
<body>
    <h1>Ray Trace</h1>
    <p>This project implements the <b>Ray Trace </b> by implementing codes in provided code. </p>
    <h2>Steps Involved:</h2>
    <h3>Camera:</h3>
    <ul>
        <li><b>Camera:</b>Implemented getRay() in camera.todo.cppfunction, given the camera, size of viewfield and a pixel, return the ray travel from camera to this pixel.</li>
        
    </ul>
    <h3>Lights:</h3>
    <ul>
        <li>Based on pointLight.todo.cpp, completed spotLight.todo.cpp and directionalLight.todo.cpp.</li>
        <li><b>spotLight.todo.cpp:</b> Implemented getAmbient(), getDiffuse(), getSpecular(), transparency() and isInShadow() functions. Almost everything is same as pointlight except the cutoff angle and dropoff rate are considered.</li>
        <li><b>directionalLight.todo.cpp:</b> Implemented getAmbient(), getDiffuse(), getSpecular(), transparency() and isInShadow() functions. Almost everything is same as pointlight except there is no attenuation coefficiences.</li>
    </ul>
    <h3>Shapes:</h3>
    <ul>
        <li><b>Triangle:</b> Implemented intersect() function. I didn't use the barycentric coordinates. First use the normal vector calculating the hitpoint of ray and plain. Then use crossproduct to determine whether this hitpoint is in the triangle. Finally use the method of vector combination to calculate the coordinates of the hit point in the plane coordinate system.</li>
        <li><b>Torus:</b> Implemented intersect() function. The polynomial.h is used to solve the quartic equation. I modified the CMakeLists.txt in Util and Ray to link the executables.</li>
        <li><b>Cone:</b> Implemented intersect() function. The cones have a side and a base, so I calculated the t of ray hit the side and ray hit the base. And take the minimum positive t as solution.</li>
    </ul>
    <h2>Test Results:</h2>
    <p>Below are the result of sphere, cone and torus under several lights.</p>

    
"""

# Add each image as an embedded base64 image in the HTML
for i, (image_filename, image_base64) in enumerate(image_base64_list):
    html_content += f"""
    <h4>IMage{i+1} ({image_filename}):</h4>
    <img src="data:image/png;base64,{image_base64}" alt="Image {i+1}" width="600">
    <br><br>
    """
html_content+="""
    <p>Below are the results of art.</p>
"""

for i, (image_filename, image_base64) in enumerate(image_unittest_base64_list):
    html_content += f"""
    <h4>Image {i+1} ({image_filename}):</h4>
    <img src="data:image/png;base64,{image_base64}" alt="Image {i+1}" width="600">
    <br><br>
    """




html_content += f"""
</body>
</html>
"""

# Save the HTML content to a file
html_file_path = 'ray_trace.html'
with open(html_file_path, 'w') as file:
    file.write(html_content)

print(f"HTML file generated: {html_file_path}")
