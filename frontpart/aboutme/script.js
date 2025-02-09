
const totalImages = 28;
for (let i = 2; i <= totalImages; i++) {
    const box = document.createElement("div"); // 创建 div 盒子
    box.className = "box";

    const img = document.createElement("img"); // 创建 img 元素
    img.src = `../images/${i}.jpg`; // 图片路径自动设置为 1.jpg, 2.jpg, ..., n.jpg
    img.alt = `Image ${i}`;

    box.appendChild(img); // 将 img 放入 div 盒子
    document.body.appendChild(box); // 将盒子放入容器中
}

const boxes = document.querySelectorAll('.box')

window.addEventListener('scroll',checkBoxes);

checkBoxes()
function checkBoxes(){
    const triggerBottom=window.innerHeight*(0.9)
    boxes.forEach(box=>{
        const boxTop=box.getBoundingClientRect().top
        if(boxTop<triggerBottom){
            box.classList.add('show')
        }else{
            box.classList.remove('show')
        }
    })
}

