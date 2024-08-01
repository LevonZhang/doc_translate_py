import streamlit as st
from docx import Document
import google.generativeai as genai
import os

# 从 Vercel 环境变量中获取 API 密钥
api_key = os.environ.get("GOOGLE_API_KEY")

# 检查是否成功获取 API 密钥
if not api_key:
    st.error("未设置 GOOGLE_API_KEY 环境变量！")
    st.stop()  # 停止应用加载

# 设置 API 密钥
genai.configure(api_key=api_key)

# 选择 Gemini Pro 模型
model = genai.get_model("gemini-pro")

# Streamlit 应用标题
st.title("Word 文档翻译 (使用 Gemini API)")

# 文件上传
uploaded_file = st.file_uploader("上传 Word 文档 (.docx)", type=["docx"])

# 目标语言选择
target_language = st.selectbox("选择目标语言", ["zh-CN", "en", "ja", "ko", "fr", "de", "es"])

# 双语模式选择
bilingual = st.checkbox("双语对照模式", True)

def translate_text(text):
    """使用 Google Gemini API 翻译文本"""
    response = model.generate_content(
        prompt=f"Translate the following text to {target_language}: {text}",
    )
    return response.text

def translate_document(document):
    """翻译整个文档"""
    for paragraph in document.paragraphs:
        original_text = paragraph.text.strip()
        if original_text:
            translated_text = translate_text(original_text)
            if bilingual:
                # 双语模式，在原段落后添加翻译
                run = paragraph.add_run("\n" + translated_text)
                run.font.italic = True 
            else:
                # 非双语模式，直接替换原文
                paragraph.text = translated_text
    return document

# 翻译按钮
if st.button("开始翻译") and uploaded_file is not None:
  try:
    # 读取 Word 文档
    doc = Document(uploaded_file)

    # 翻译文档
    translated_doc = translate_document(doc)

    # 保存翻译后的文档
    translated_doc.save("translated_document.docx")

    # 提供下载链接
    st.download_button(
      "下载翻译后的文档", 
      open("translated_document.docx", "rb").read(),
      file_name="translated_document.docx"
    )

  except Exception as e:
    st.error(f"翻译过程中出现错误：{e}")