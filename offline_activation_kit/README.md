# Offline Activation Kit

这个目录是一个可独立复用的离线授权工具包，适合放进别的桌面程序里继续使用。

它实现的是这套流程：

1. 客户启动程序后看到本机机器码。
2. 客户把机器码发给你。
3. 你用密钥生成器生成 `.key` 激活文件或激活串。
4. 客户把密钥导入程序。
5. 程序校验机器码、签名、公钥、产品编号和到期时间。
6. 如果程序被复制到另一台电脑，机器码变化，旧密钥自动失效。

## 目录说明

- [activation.py](/D:/11111/1case/076_xjy/offline_activation_kit/activation.py)
  - 通用授权核心，不依赖你的业务代码。
- [dialog.py](/D:/11111/1case/076_xjy/offline_activation_kit/dialog.py)
  - 客户侧激活弹窗。
- [generator_app.py](/D:/11111/1case/076_xjy/offline_activation_kit/generator_app.py)
  - 你自己使用的发码工具。
- [integration_example.py](/D:/11111/1case/076_xjy/offline_activation_kit/integration_example.py)
  - 最小接入示例。

## 复用方式

把整个 `offline_activation_kit` 目录复制到你的新项目里，然后至少修改这 3 个配置项：

```python
CONFIG = ActivationConfig(
    app_name="你的软件名",
    product_id="your-product-id",
    storage_dir_name=".your_app",
    key_prefix="YOURAPP-LIC-1.",
)
```

建议每个软件都用不同的：

- `product_id`
- `storage_dir_name`
- `key_prefix`

这样不同程序之间的授权不会串。

## 客户程序接入

你可以参考 [integration_example.py](/D:/11111/1case/076_xjy/offline_activation_kit/integration_example.py)。

核心就是启动主窗口前先校验授权：

```python
runtime_root = resolve_runtime_root()
manager = LicenseManager(runtime_root, CONFIG)
status = manager.current_status()
if not status.valid:
    dialog = LicenseActivationDialog(manager, validation_result=status)
    if not dialog.exec():
        return 1
```

## 你这边如何发码

运行：

```powershell
py -3.12 offline_activation_kit\generator_app.py
```

首次运行会自动生成：

- `.secrets\license_private_key.pem`
- `.secrets\license_public_key.pem`
- `publish\license_public_key.pem`

注意：

- 私钥只能你自己保存，绝对不要发给客户。
- 客户程序里只放 `publish\license_public_key.pem`。
- 如果重新生成了私钥，就必须重新把公钥放进客户程序并重新打包。

## 建议接入顺序

1. 把 `offline_activation_kit` 复制到新项目。
2. 修改 `generator_app.py` 和客户端入口里的 `CONFIG`。
3. 把 `publish\license_public_key.pem` 放到你的程序运行目录，或打包进 `_internal`。
4. 在主窗口启动前调用授权校验。
5. 打包程序。
6. 客户发送机器码给你后，你再生成对应 `.key` 文件发回去。

## 这套方案的边界

它能很好解决：

- 程序复制到新电脑后不能直接用
- 每台电脑单独授权
- 你可以控制是否重新签发

它不能绝对解决：

- 有经验的人逆向修改程序逻辑
- 客户把已激活环境整机克隆

如果以后你要继续加固，可以在此基础上再加：

- 核心功能二次验签
- 导出结果水印
- 在线激活次数控制
- 核心算法编译为 `.pyd`
