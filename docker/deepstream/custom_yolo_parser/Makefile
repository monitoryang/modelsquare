CUDA_VER ?= 12.8

CC := g++
CFLAGS := -Wall -std=c++14 -shared -fPIC -O2 -Wno-error=deprecated-declarations
CFLAGS += -I/opt/nvidia/deepstream/deepstream/sources/includes \
          -I/opt/nvidia/deepstream/deepstream/sources/includes/nvdsinferserver \
          -I/usr/local/cuda-$(CUDA_VER)/include

LIBS := -L/opt/nvidia/deepstream/deepstream/lib/ -lnvds_meta
PKGS := glib-2.0
CFLAGS += $(shell pkg-config --cflags $(PKGS))
LIBS   += $(shell pkg-config --libs $(PKGS))

LFLAGS := -Wl,--start-group $(LIBS) -Wl,--end-group

SRC := nvdsinferserver_custom_yolov8.cpp
TARGET := libnvdsinferserver_custom_yolov8.so

all: $(TARGET)

$(TARGET): $(SRC)
	$(CC) -o $@ $^ $(CFLAGS) $(LFLAGS)

clean:
	rm -f $(TARGET)
