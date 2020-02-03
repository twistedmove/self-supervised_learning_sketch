import torch
import torch.utils.data as data
import torchvision
import torchnet as tnt
import torchvision.datasets as datasets
import torchvision.transforms as transforms
import numpy as np
import random
from torch.utils.data.dataloader import default_collate
from quickdraw_transform import deform_xy
from PIL import Image
import os
import numpy as np
import sys
import csv


# Set the paths of the datasets here.
# _sketch_dataset_root = "/home/songzeyu/quickdraw_224png_20190108"

def _get_filenames_and_classes(dataset_dir):
    """Returns a list of filenames and inferred class names.

    Args:
      dataset_dir: A directory containing a set of subdirectories representing
        class names. Each subdirectory should contain PNG or JPG encoded images.

    Returns:
      A list of image file paths, relative to `dataset_dir` and the list of
      subdirectories, representing class names.
    """
    quickdraw_root = dataset_dir
    directories = []
    class_names = []
    for filename in os.listdir(quickdraw_root):
        path = os.path.join(quickdraw_root, filename)
        if os.path.isdir(path):
            directories.append(path)
            class_names.append(filename)

    photo_filenames = []
    for directory in directories:
        for filename in os.listdir(directory):
            path = os.path.join(directory, filename)
            photo_filenames.append(path)

    return photo_filenames, sorted(class_names)

class SketchDataset(data.Dataset):

    def __init__(self, split, resize, root):
        '''
        args:
          dataset_name:数据集名称
          split:train/test   
        output:
          a dataset instance     
        '''
        self.split = split.lower()             
        assert(self.split=='train' or self.split=='test')
        if resize:
            transforms_list = [
            transforms.Resize(299),
            lambda x: np.asarray(x),
            ]
        else:
            transforms_list = [
            lambda x: np.asarray(x),
            ]  
        # 分割训练集及测试集，得到训练集测试集路径
        _NUM_VALIDATION = 345000
        _RANDOM_SEED = 0  
        photo_filenames, _ = _get_filenames_and_classes(_sketch_dataset_root)
        random.seed(_RANDOM_SEED)
        random.shuffle(photo_filenames)
        if self.split == "train":
            self.image_list = photo_filenames[_NUM_VALIDATION:]            
        elif self.split == "test":
            self.image_list = photo_filenames[:_NUM_VALIDATION]
        self.transform = transforms.Compose(transforms_list)         
        

    def __getitem__(self, index):
        image = Image.open(self.image_list[index])
        image = self.transform(image)
        return image

    def __len__(self):
        return len(self.image_list)

def rotate_img(img, rot):
    if rot == 0: # 0 degrees rotation
        return img
    elif rot == 90: # 90 degrees rotation
        return np.flipud(np.transpose(img, (1,0,2))).copy()
    elif rot == 180: # 90 degrees rotation
        return np.fliplr(np.flipud(img)).copy()
    elif rot == 270: # 270 degrees rotation / or -90
        return np.transpose(np.flipud(img).copy(), (1,0,2))
    else:
        raise ValueError('rotation should be 0, 90, 180, or 270 degrees')

class DataLoader(object):
    """
    args:
      dataset: a dataset instance     
    output:
      a dataloader instance   
    """
    def __init__(self,
                 dataset,
                 batch_size=1,
                 unsupervised=True,
                 epoch_size=None,
                 num_workers=0,
                 shuffle=True):
        self.dataset = dataset
        self.shuffle = shuffle
        self.epoch_size = epoch_size if epoch_size is not None else len(dataset)
        self.batch_size = batch_size
        self.unsupervised = unsupervised
        self.num_workers = num_workers
        self.transform = transforms.Compose([
              transforms.ToTensor(), #numpy to tensor               
              ]) 
        self.inv_transform=transforms.Compose([              
              lambda x:x.numpy()*255.0,
              lambda x:x.transpose(1,2,0).astype(np.uint8)
              ])


    def get_iterator(self, epoch=0):
        rand_seed = epoch * self.epoch_size
        random.seed(rand_seed)
        if self.unsupervised:
            #无监督，四个方向旋转四分类
            def _load_function(idx):                    
                idx = idx % len(self.dataset)
                img0 = self.dataset[idx]
                transformed_imgs = [
                #原图
                self.transform(img0), 
                #90
                self.transform(rotate_img(img0, 90)),
                #180            
                self.transform(rotate_img(img0, 180)), 
                #270 
                self.transform(rotate_img(img0, 270)),                          
                ]
                transform_labels=torch.LongTensor([0,1,2,3]) #labels 
                return torch.stack(transformed_imgs, dim=0), transform_labels
            def _collate_fun(batch):
                batch = default_collate(batch)
                assert(len(batch)==2)
                batch_size, transform_num, channels, height, width = batch[0].size()
                batch[0] = batch[0].view([batch_size*transform_num, channels, height, width])
                batch[1] = batch[1].view([batch_size*transform_num])
                return batch
        else: 
            #监督
            def _load_function(idx):
                idx = idx % len(self.dataset)
                img, categorical_label = self.dataset[idx]
                img = self.transform(img)
                return img, categorical_label
            _collate_fun = default_collate

        tnt_dataset = tnt.dataset.ListDataset(elem_list=range(self.epoch_size),
                                              load=_load_function)
        data_loader = tnt_dataset.parallel(batch_size=self.batch_size,
             collate_fn=_collate_fun, num_workers=self.num_workers,
             shuffle=self.shuffle)
        return data_loader

    def __call__(self, epoch=0):
        return self.get_iterator(epoch)

    def __len__(self):
        return self.epoch_size // self.batch_size

