"""量化交易学习项目的核心包。

包含四个相互独立的模块，数据流向单向清晰：
    data -> strategies -> backtest -> plotting

任何模块都不依赖 Streamlit，app.py 只是把它们组装成网页界面。
"""
