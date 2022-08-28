# Copyright (c) 2015-present, Facebook, Inc.
# All rights reserved.
from configparser import Interpolation
import os
import random

import torch
from torch.utils.data.dataset import Subset
from torchvision import datasets, transforms
from torchvision.transforms.transforms import Lambda

from timm.data.constants import IMAGENET_DEFAULT_MEAN, IMAGENET_DEFAULT_STD
from timm.data import create_transform

import utils

CIFAR10_MEAN = (0.4914, 0.4822, 0.4465)
CIFAR10_STD = (0.2471, 0.2435, 0.2616)
CIFAR100_MEAN = (0.5071, 0.4867, 0.4408)
CIFAR100_STD = (0.2675, 0.2565, 0.2761)

class ContinualDataLoader:
    def __init__(self, args):
        self.args = args
        if not os.path.exists(self.args.data_path):
            os.makedirs(self.args.data_path)
        self.transform_train = build_transform(True, self.args)
        self.transform_val = build_transform(False, self.args)
        self._get_dataset(self.args.dataset)

    def _get_dataset(self, name):
        if name == 'CIFAR100':
            root = self.args.data_path
            self.dataset_train = datasets.CIFAR100(root=root, train = True, download = True, transform = self.transform_train)
            self.dataset_val = datasets.CIFAR100(root =root, train = False, transform = self.transform_val)
            self.args.nb_classes = 100
        
        else:
            raise NotImplementedError(f"Not supported dataset: {self.args.dataset}")
        
    def create_dataloader(self):
        dataloader, class_mask = self.split()
        
        return dataloader, class_mask
    
    def target_transform(self, x):
        # Target transform form splited dataset, 0~9 -> 0~9, 10~19 -> 0~9, 20~29 -> 0~9..
        return x - 10*(x//10)

    def split(self):
        dataloader = []
        labels = [i for i in range(self.args.nb_classes)] # [0, 1, 2, ..., 99]
        
        if self.args.shuffle:
            random.shuffle(labels)
        
        class_mask = list() if self.args.task_inc or self.args.train_mask else None
        
        for _ in range(self.args.num_tasks):
            train_split_indices = []
            test_split_indices = []
            
            scope = labels[:self.args.classes_per_task]
            labels = labels[self.args.classes_per_task:]
            
            if class_mask is not None:
                class_mask.append(scope)

            for k in range(len(self.dataset_train.targets)):
                if int(self.dataset_train.targets[k]) in scope:
                    train_split_indices.append(k)
                    
            for h in range(len(self.dataset_val.targets)):
                if int(self.dataset_val.targets[h]) in scope:
                    test_split_indices.append(h)
            
            # self.dataset_train.target_transform = Lambda(self.target_transform)
            # self.dataset_val.target_transform = Lambda(self.target_transform)

            dataset_train, dataset_val =  Subset(self.dataset_train, train_split_indices), Subset(self.dataset_val, test_split_indices)

            data_loader_train = torch.utils.data.DataLoader(
                dataset_train, 
                batch_size=self.args.batch_size,
                num_workers=self.args.num_workers,
                pin_memory=self.args.pin_mem,
                drop_last=True,
            )

            data_loader_val = torch.utils.data.DataLoader(
                dataset_val, 
                batch_size=int(1.5 * self.args.batch_size),
                num_workers=self.args.num_workers,
                pin_memory=self.args.pin_mem,
                drop_last=False
            )

            dataloader.append({'train': data_loader_train, 'val': data_loader_val})
        
        return dataloader, class_mask


def build_transform(is_train, args):
    resize_im = args.input_size > 32
    if is_train:
        # this should always dispatch to transforms_imagenet_train
        transform = create_transform(
            input_size=args.input_size,
            is_training=True,
            color_jitter=args.color_jitter,
            auto_augment=args.aa,
            interpolation=args.train_interpolation,
            re_prob=args.reprob,
            re_mode=args.remode,
            re_count=args.recount,
        )
        if not resize_im:
            # replace RandomResizedCropAndInterpolation with
            # RandomCrop
            transform.transforms[0] = transforms.RandomCrop(
                args.input_size, padding=4)
        return transform

    t = []
    if resize_im:
        size = int((256 / 224) * args.input_size)
        t.append(
            transforms.Resize(size, interpolation=3),  # to maintain same ratio w.r.t. 224 images
        )
        t.append(transforms.CenterCrop(args.input_size))

    t.append(transforms.ToTensor())

    t.append(transforms.Normalize(IMAGENET_DEFAULT_MEAN, IMAGENET_DEFAULT_STD))
    
    return transforms.Compose(t)