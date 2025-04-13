# Think-Probe

一个会思考的智能体应用

## 准备工作

配置config.yml中需要的key

## 本地开发

安装依赖

```shell
pip install pdm
pdm install
```

运行run.py启动服务，访问http://127.0.0.1:8080页面即可开始聊天

## 根据当前架构打包镜像

```shell
make
```

## 指定架构打包镜像

```shell
make linux-amd64
```

