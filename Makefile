VERSION=1.0.0
# 系统信息检测
OS := $(shell uname -s)
ARCH := $(shell uname -m)

# 支持的架构映射
SUPPORTED_LINUX_ARCH := x86_64:aarch64
SUPPORTED_DARWIN_ARCH := arm64

# 目标架构映射
ARCH_TARGET_x86_64 := amd64
ARCH_TARGET_aarch64 := arm64
ARCH_TARGET_arm64 := arm64

# 根据系统和架构确定目标
ifeq ($(OS),Linux)
    ifneq ($(filter $(ARCH),$(subst :, ,$(SUPPORTED_LINUX_ARCH))),)
        TARGET := linux-$(ARCH_TARGET_$(ARCH))
    else
        $(error Unsupported Linux architecture: $(ARCH). Supported: $(SUPPORTED_LINUX_ARCH))
    endif
else ifeq ($(OS),Darwin)
    ifneq ($(filter $(ARCH),$(subst :, ,$(SUPPORTED_DARWIN_ARCH))),)
        TARGET := linux-$(ARCH_TARGET_$(ARCH))
    else
        $(error Unsupported macOS architecture: $(ARCH). Supported: $(SUPPORTED_DARWIN_ARCH))
    endif
else
    $(error Unsupported OS: $(OS). Supported: Linux, Darwin)
endif

# 默认执行目标
.DEFAULT_GOAL := build

.PHONY: build linux-amd64 linux-arm64 clean

# 构建规则
build: $(TARGET)

linux-amd64:
	@echo "Building for linux/amd64..."
	docker buildx build --platform linux/amd64 -t think-probe-amd64:$(VERSION) -o type=docker .

linux-arm64:
	@echo "Building for linux/arm64..."
	docker buildx build --platform linux/arm64 -t think-probe-arm64:$(VERSION) -o type=docker .

clean:
	docker buildx prune -f