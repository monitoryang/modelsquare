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

# OWL parser additionally needs CUDA runtime for cudaMemcpy (GPU→CPU→GPU)
OWL_LFLAGS := -Wl,--start-group $(LIBS) -L/usr/local/cuda-$(CUDA_VER)/lib64 -lcudart -Wl,--end-group

YOLO_SRC    := nvdsinferserver_custom_yolov8.cpp
YOLO_TARGET := libnvdsinferserver_custom_yolov8.so

OWL_SRC     := nvdsinferserver_custom_owl.cpp
OWL_TARGET  := libnvdsinferserver_custom_owl.so

all: $(YOLO_TARGET) $(OWL_TARGET)

$(YOLO_TARGET): $(YOLO_SRC)
	$(CC) -o $@ $^ $(CFLAGS) $(LFLAGS)

$(OWL_TARGET): $(OWL_SRC)
	$(CC) -o $@ $^ $(CFLAGS) $(OWL_LFLAGS)

clean:
	rm -f $(YOLO_TARGET) $(OWL_TARGET)
