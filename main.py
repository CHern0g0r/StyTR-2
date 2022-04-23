import argparse
from pathlib import Path
import os
import torch
import torch.nn as nn
from PIL import Image
from os.path import basename
from os.path import splitext
from torchvision import transforms
from torchvision.utils import save_image
from function import calc_mean_std, normal, coral
import models.transformer as transformer
import models.StyTR as StyTR
import matplotlib.pyplot as plt
from matplotlib import cm
from function import normal
import numpy as np
import time
from distutils.dir_util import copy_tree


def test_transform(size, crop):
    transform_list = []
   
    if size != 0: 
        transform_list.append(transforms.Resize(size))
    if crop:
        transform_list.append(transforms.CenterCrop(size))
    transform_list.append(transforms.ToTensor())
    transform = transforms.Compose(transform_list)
    return transform
def style_transform(h,w):
    k = (h,w)
    size = int(np.max(k))
    print(type(size))
    transform_list = []    
    transform_list.append(transforms.CenterCrop((h,w)))
    transform_list.append(transforms.ToTensor())
    transform = transforms.Compose(transform_list)
    return transform

def content_transform():
    
    transform_list = []   
    transform_list.append(transforms.ToTensor())
    transform = transforms.Compose(transform_list)
    return transform

  

parser = argparse.ArgumentParser()
# Basic options
parser.add_argument('--content', type=str,
                    help='File path to the content image')
parser.add_argument('--content_dir', type=str,
                    help='Directory path to a batch of content images')
parser.add_argument('--style', type=str,
                    help='File path to the style image, or multiple style \
                    images separated by commas if you want to do style \
                    interpolation or spatial control')
parser.add_argument('--style_dir', type=str,
                    help='Directory path to a batch of style images')
parser.add_argument('--output', type=str, default='output',
                    help='Directory to save the output image(s)')
parser.add_argument('--vgg', type=str, default='./experiments/vgg_normalised.pth')
parser.add_argument('--decoder_path', type=str, default='experiments/decoder_iter_160000.pth')
parser.add_argument('--Trans_path', type=str, default='experiments/transformer_iter_160000.pth')
parser.add_argument('--embedding_path', type=str, default='experiments/embedding_iter_160000.pth')


parser.add_argument('--style_interpolation_weights', type=str, default="")
parser.add_argument('--a', type=float, default=1.0)
parser.add_argument('--position_embedding', default='sine', type=str, choices=('sine', 'learned'),
                        help="Type of positional embedding to use on top of the image features")
parser.add_argument('--hidden_dim', default=512, type=int,
                        help="Size of the embeddings (dimension of the transformer)")
args = parser.parse_args()




# Advanced options
content_size=512
style_size=512
crop='store_true'
save_ext='.jpg'
output_dir=Path(args.output)
preserve_color='store_true'
alpha=args.a




device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

# Either --content or --content_dir should be given.
if args.content:
    content_paths = [Path(args.content)]
else:
    content_dir = Path(args.content_dir)
    # content_paths = [f for f in content_dir.glob('*')]

# Either --style or --style_dir should be given.
if args.style:
    style_paths = [Path(args.style)]    
else:
    style_dir = Path(args.style_dir)
    # style_paths = [f for f in style_dir.glob('*')]

if not os.path.exists(output_dir):
    os.mkdir(output_dir)


vgg = StyTR.vgg
vgg.load_state_dict(torch.load(args.vgg))
vgg = nn.Sequential(*list(vgg.children())[:44])

decoder = StyTR.decoder
Trans = transformer.Transformer()
embedding = StyTR.PatchEmbed()

decoder.eval()
Trans.eval()
vgg.eval()
from collections import OrderedDict
new_state_dict = OrderedDict()
state_dict = torch.load(args.decoder_path)
for k, v in state_dict.items():
    #namekey = k[7:] # remove `module.`
    namekey = k
    new_state_dict[namekey] = v
decoder.load_state_dict(new_state_dict)

new_state_dict = OrderedDict()
state_dict = torch.load(args.Trans_path)
for k, v in state_dict.items():
    #namekey = k[7:] # remove `module.`
    namekey = k
    new_state_dict[namekey] = v
Trans.load_state_dict(new_state_dict)

new_state_dict = OrderedDict()
state_dict = torch.load(args.embedding_path)
for k, v in state_dict.items():
    #namekey = k[7:] # remove `module.`
    namekey = k
    new_state_dict[namekey] = v
embedding.load_state_dict(new_state_dict)

network = StyTR.StyTrans(vgg,decoder,embedding,Trans,args)
network.eval()
network.to(device)



content_tf = test_transform(content_size, crop)
style_tf = test_transform(style_size, crop)

styles = []
for style_img in style_dir.iterdir():
    if style_img.suffix == '.jpg':
        style = style_tf(Image.open(style_img).convert("RGB")).unsqueeze(0)
        styles.append(style)

print(f'Number of styles: {len(styles)}')

style_idx = 0

output_dir.mkdir(exist_ok=True, parents=True)

for directory in content_dir.iterdir():
    dir_name = directory.name
    print(dir_name)

    new_directory = output_dir / dir_name
    new_directory.mkdir(exist_ok=True, parents=True)

    for target in directory.iterdir():
        if target.is_dir():
            inner_dir_name = target.name
            new_inner_path = new_directory / inner_dir_name
            copy_tree(str(target), str(new_inner_path))
        elif target.suffix == '.png':
            content_name = target.name
            output_path = new_directory / content_name

            cur_style = styles[style_idx % len(styles)]
            cur_style = cur_style.to(device)

            style_idx = (style_idx + 1) % len(styles)

            content = content_tf(Image.open(target).convert("RGB"))
            content = content.unsqueeze(0).to(device)

            with torch.no_grad():
                output = network(content, cur_style)       
            output = output.cpu()

            cur_style = cur_style.to('cpu')

            save_image(output, output_path)
            # print(output_path)
