import streamlit as st
from docx import Document
import google.generativeai as genai
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# --- 全局变量 ---
# 从 Vercel 环境变量中获取 API 密钥
api_key = os.environ.get("GOOGLE_API_KEY")

# 检查是否成功获取 API 密钥
if not api_key:
    st.error("未设置 GOOGLE_API_KEY 环境变量！")
    st.stop()  # 停止应用加载

# 设置 API 密钥
genai.configure(api_key=api_key)

# 选择 Gemini Pro 模型
model = genai.GenerativeModel('gemini-1.5-flash')

# Streamlit 应用标题
st.title("Word 文档翻译")

# 文件上传
uploaded_file = st.file_uploader("上传 Word 文档 (.docx)", type=["docx"])

# 目标语言选择
target_language = st.selectbox("选择目标语言", ["zh-CN", "en", "ja", "ko", "fr", "de", "es"])

# 双语模式选择
bilingual = st.checkbox("双语对照模式", True)

# --- 翻译进度条 ---
progress_bar = st.progress(0, text="准备翻译...")
progress_lock = threading.Lock() # 用于进度条更新的线程锁
total_elements = 0
completed_elements = 0

def update_progress(increment=1):
    """更新进度条"""
    global completed_elements
    with progress_lock:
        completed_elements += increment
        progress = int((completed_elements / total_elements) * 100)
        progress_bar.progress(progress, text=f"正在翻译... ({progress}%)")

def translate_text(text):
    """使用 Google Gemini API 翻译文本"""
    response = model.generate_content(f"Translate the following text to {target_language}: {text}")
    return response.text

def process_paragraph(paragraph):
    """处理单个段落，包含翻译和进度更新"""
    original_text = paragraph.text.strip()
    if original_text:
        translated_text = translate_text(original_text)
        if bilingual:
            paragraph.add_run("\n" + translated_text)
        else:
            paragraph.text = translated_text
    update_progress() # 更新进度

def process_run(run):
    """处理单个run，包含翻译和进度更新"""
    original_text = run.text.strip()
    if original_text:
        translated_text = translate_text(original_text)
        if bilingual:
            run.font.italic = True  # 将翻译结果设置为斜体
            run.add_text(" " + translated_text) 
        else:
            run.text = translated_text
    update_progress() # 更新进度

def translate_document(document):
    """使用多线程翻译文档"""
    global total_elements, completed_elements
    total_elements = sum(len(paragraph.runs) for paragraph in document.paragraphs) + sum(
        len(cell.paragraphs) for table in document.tables for row in table.rows for cell in row.cells
    )
    completed_elements = 0

    with ThreadPoolExecutor() as executor:
        # 提交段落翻译任务
        paragraph_futures = [executor.submit(process_paragraph, paragraph) for paragraph in document.paragraphs]

        # 提交表格单元格中run的翻译任务
        run_futures = []
        for table in document.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        for run in paragraph.runs:
                            run_futures.append(executor.submit(process_run, run))

        # 等待所有任务完成
        for _ in as_completed(paragraph_futures + run_futures):
            pass

    return document


# 翻译按钮
if st.button("开始翻译") and uploaded_file is not None:
    try:
        # 读取 Word 文档
        doc = Document(uploaded_file)
        # 翻译文档
        translated_doc = translate_document(doc)
        # 保存翻译后的文档
        translated_file_name = f"translated_{uploaded_file.name}"
        translated_doc.save(translated_file_name)
        # 提供下载链接
        with open(translated_file_name, "rb") as f:
            st.download_button(
                label="下载翻译后的文档",
                data=f,
                file_name=translated_file_name,
            )
    except Exception as e:
        st.error(f"翻译过程中出现错误：{e}")