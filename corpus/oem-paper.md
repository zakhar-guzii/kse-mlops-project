# OpenEarthMap: A Benchmark Dataset for Global High-Resolution Land Cover Mapping

## Abstract

We introduce OpenEarthMap, a benchmark dataset, for global high-resolution land cover mapping. OpenEarthMap consists of 2.2 million segments of 5000 aerial and satellite images covering 97 regions from 44 countries across 6 continents, with manually annotated 8-class land cover labels at a 0.25–0.5m ground sampling distance. Semantic segmentation models trained on the OpenEarthMap generalize worldwide and can be used as off-the-shelf models in a variety of applications. We evaluate the performance of state-of-the-art methods for unsupervised domain adaptation and present challenging problem settings suitable for further technical development. We also investigate lightweight models using automated neural architecture search for limited computational resources and fast mapping. The dataset is available at https://open-earth-map.org.

Table 1: Summary of remote sensing benchmark datasets for semantic segmentation. B: building extraction, R: road extraction, LC: land cover mapping, and CD: change detection. The number of segments was counted on available labels.

| Image level | GSD (m) | Dataset | Task | Classes | Countries | Regions | Area ( km^2 ) | Segments |
|---|---|---|---|---|---|---|---|---|
| Meter level | 10 | OpenSentinelMap | LC | 15 | — | — | 505,202 | 3,467,552 |
| Meter level | 3 | DynamicEarthNet | LC/CD | 7 | — | 75 | 707 | 897,855 |
| Sub-meter level | 0.3–0.5 | SpaceNet 1&2 | B | 2 | 5 | 5 | 5,555 | 685,235 |
| Sub-meter level | 0.5/0.3/0.5 | DeepGlobe | R/B/LC | 2/2/7 | — | — | 2,220/984/1,717 | —/302,701/20,697 |
| Sub-meter level | 0.02–0.2 | Open Cities AI | B | 2 | 8 | 11 | 419 | 792,484 |
| Sub-meter level | 0.5 | xBD | B/CD | 2/4 | 15 | 21 | 3,382 | 850,736 |
| Sub-meter level | 0.3 | LoveDA | LC | 7 | 1 | 3 | 536 | 166,768 |
| Sub-meter level | 0.25–0.5 | OpenEarthMap | LC | 8 | 44 | 97 | 799 | 2,205,395 |

## 1 Introduction

Land cover classification maps are the basic information for decision making in various applications, such as land use planning, food security, resource management, and disaster response. Meter-level resolution satellite imagery have been used to map the world, as represented by GlobeLand30 , FROM-GLC , and recent benchmarks such as OpenSentinelMap  and DynamicEarthNet . Satellite imagery at a sub-meter level of ground sampling distance (GSD) enables the extraction of core map information such as buildings and roads. In recent years, there has been substantial progress in automatic construction of building footprints over large areas .

Since the advent of deep learning , a great deal of effort has been devoted to developing benchmark datasets for high-resolution remote sensing image analysis to facilitate advances in theory and practice. SpaceNet  and IEEE GRSS DFC , among others, regularly introduce benchmark datasets to the public through competitions that drive research and development. Building detection, road detection, object detection, and land cover classification (semantic segmentation) are the most typical tasks for which these datasets are used in supervised learning . Apart from supervised learning, these datasets have been used in more realistic problems, including transfer learning , semi-supervised learning  and weakly supervised learning . Benchmark datasets that contribute to solving social problems regarding change detection and disaster damage mapping have been developed as well .

Benchmark datasets for semantic segmentation at sub-meter level resolution have two problems: regional disparity and annotation quality. The regions included in many benchmarks are often biased toward developed countries. Thus, benchmark datasets for regions where map information is not well maintained are scarce. Two main reasons why this problem has not been easily solved are the lack of high-resolution open aerial imagery in developing countries and that commercial high-resolution satellite imagery are basically not redistributable. Other than buildings and roads, the annotation quality of land cover labeling in existing benchmarks is coarse, even though images are at sub-meter level resolution. This is due to the high cost of manually labeling sub-meter-resolution imagery in spatial detail. Thus, most of the labeling data are based on OpenStreetMap  and open map data from local governments.

In this work, we propose OpenEarthMap, a benchmark dataset for global high-resolution land cover mapping with the goal of providing automated mapping for everyone. OpenEarthMap presents a major advance over existing data with respect to geographic diversity and annotation quality (see Table 1). OpenEarthMap consists of 8-class land cover labels at a 0.25–0.5m GSD of 5000 images, covering 97 regions from 44 countries across 6 continents. We adopted RGB images of some existing benchmark datasets for building detection and collected additional images for areas not covered by these benchmarks to balance the regional disparities. All images were manually labeled to ensure high-quality annotation. We evaluate the performance of state-of-the-art methods for semantic segmentation and unsupervised domain adaptation tasks and identify problem settings suitable for further technical development. In addition, lightweight models based on automated neural architectural search are investigated for cases where people requiring automated mapping have limited computational resources or for rapid mapping applications such as disaster response.

## 2 The Dataset

### 2.1 Source of Imagery

Our strategy is to reuse images from existing benchmark datasets as much as possible and manually annotate new land cover labels. We selected xBD , Inria , Open Cities AI , SpaceNet , Landcover.ai , AIRS , GeoNRW , and HTCD  datasets based on the condition that the source images are redistributable, the ground sampling distance (GSD) is equal to or less than 0.5m, and the images have geocoordinate information. If there are enough images of a region, which we defined at a scale of province or city, we sampled 50–70 images of that region at a size of 1024×1024 pixels. The number of images from each dataset we adopted was determined based on the diversity and balance of the continents and countries where the images were taken. For countries and regions not covered by the existing datasets, aerial images publicly available in such countries or regions were collected to mitigate the regional gap, which is an issue in most of the existing benchmark datasets. The open data were downloaded from OpenAerialMap  and geospatial agencies . See the supplementary for more details of attribution.

In addition to this geographic diversity, our dataset includes a mixture of images taken from different platforms, including satellite, aircraft, and UAV. For very high-resolution images with GSD less than 0.25m, we resampled the images to 0.3m or 0.5m to account for object size and visual interpretability of the captured area. Basically, the images were selected by a combination of random sampling and manual checking for each region. Moreover, if the number of images of a particular region is very large in the source benchmark dataset, we trained a segmentation model using sequentially labeled data (e.g., every 10 images) and another regression model to estimate the loss. Then, we added the images that have high values of predicted loss, as they are more difficult by a model trained with the available labels to segment.

In the end, we collected a total of 5000 images from 97 regions of six continents. Figure  shows annotated samples and the geographic distribution of the 97 regions with different colors indicating the source datasets. Figure 2 depicts the number of images in our dataset for each of the six continents, colored to indicate the origin of the images. Asia, Africa, and South America are not well covered by the source datasets; thus, we added many images from public data to balance the regional disparities. Figure 3 presents a t-SNE 2D plot based on the similarity of image features for the 97 regions. For each region, we used the average of features extracted by EfficientNet-B4 trained as an encoder of U-Net on OpenEarthMap. The 12 representative images in the 2D plot show that different locations correspond to diverse images. It can also be seen that the different source datasets are complementary to each other, and that the diversity of images is enriched by the open data we added. The different symbols correspond to the six continents and enable the similarities between the continents to be seen. For example, regions in Europe and North America as well as Africa and South America are similar in the image features.

### 2.2 Classes, Annotations, and Data Split

Classes: We provide annotations with eight classes: bareland, rangeland, developed space, road, tree, water, agriculture land, and building. The class selection is consistent with existing products and benchmark datasets (e.g., LoveDA  and DeepGlobe ) with sub-meter GSD. Table 2 shows the number and proportion of labeled pixels and the number of segments of each class. Here, as well as in Table 1, we refer to a segment as a set of connected pixels with the same label, and it was counted using OpenCV’s findContours function. It can be seen that the elevated objects (e.g., tree and building) are finely annotated compared to the ground objects (e.g., agriculture land). As can be seen in the horizontal bar charts of 12 representative regions in Figure 3, the class proportions in the different regions are diverse.

Annotations: A total of 16 people worked on the annotation process: 8 people were responsible for annotating the images, while the remaining 8 people performed quality checks to point out errors. One person labels an image and at least two people perform the quality check. We spent a longer time labeling the first 100 images and exchanging ideas with each other to ensure that all
participants were in agreement about the class definitions. On average, the labeling took 2.5 hours per image. This is significantly longer than the 1.5 hours of Cityscapes , which illustrates the difficulty of labelling remote sensing images.
All the labeling was done manually. For the labeling of images of the existing benchmark datasets, only the building class was used as the starting point. However, since a lot of label noise was found, segments of buildings were also manually modified. The most important feature of OpenEarthMap’s labeling is its level of spatial detail. As shown in Table 1, the area covered by the images in OpenEarthMap is not very large compared to the other benchmark datasets, however, the number of segments is 10 times more than that of LoveDA.

The accuracy of human annotations is evaluated by having two different people labeling 200 images twice. We selected two or three images with as many classes as possible based on the first annotation from each region to constitute the 200 images. The percentage of pixels that were labeled as the same class in the two different annotations by different people is 78%. This percentage is significantly lower than the 96% in Cityscapes , suggesting that annotation of high-resolution remote sensing images is much more challenging than annotation of urban street scenes. The relationship between human labeling accuracy and estimation accuracy of the state-of-the-art segmentation models is discussed in Section 3.4.

Table 2: The number and proportion of pixels and the number of segments of the eight classes.

| Color (HEX) | Class | Pixels Count (M) | Pixels (%) | Segments (K) |
|---|---|---|---|---|
| 800000 | Bareland | 74 | 1.5 | 6.3 |
| 00FF24 | Rangeland | 1130 | 22.9 | 459.4 |
| 949494 | Developed space | 798 | 16.1 | 382.7 |
| FFFFFF | Road | 331 | 6.7 | 27.9 |
| 226126 | Tree | 996 | 20.2 | 902.9 |
| 0045FF | Water | 161 | 3.3 | 18.7 |
| 4BB549 | Agriculture land | 680 | 13.7 | 18.2 |
| DE1F07 | Building | 770 | 15.6 | 389.3 |

Data split: For the semantic segmentation task, the images from each region were randomly divided into training, validation, and test sets with a ratio of 6:1:3, which respectively yielded 3000, 500, and 1500 images out of the total 5000 images. To ensure that all classes in each region are included in the training set and as many classes as possible are included in the test set, the split with the least mismatch between the training and test classes was selected from multiple random trials. For the unsupervised domain adaptation (UDA) tasks, we adopt two ways of data split to investigate regional-level and continent-wise domain gaps. For regional-level UDA, the entire dataset is divided into 73 and 24 regions for source and target domains, respectively. The split was performed in such a way that both the source and the target domains consist of relatively even distribution of the countries from all six continents as well as a balance between urban and rural areas. This split is not as extreme as the urban-rural split in LoveDA but rather it is a realistic scenario in domain adaptation where OpenEarthMap is at hand as source data and adapts models for mapping in any new region, not only urban-rural adaptation. For continent-wise UDA, we use data from one continent as the source domain and other continents as the target domains.

### 2.3 Comparison with Related Datasets

Very recently, meter-level resolution benchmarks have made great progress in global land cover mapping; OpenSentinelMap  is featured in its comprehensive coverage of the globe exploiting open data of Sentinel-2 and OpenStreetMap while DynamicEarthNet  is advantageous at high-temporal resolution. OpenEarthMap goes one step further in providing spatially detailed annotation at the sub-meter level. A more detailed comparison is made with LoveDA  and DeepGlobe , which have similar resolution and class definitions as OpenEarthMap. Figure 4 shows a comparison of the class proportions of the three datasets. It should be noted that LoveDA does not include rangeland, and that in the DeepGlobe dataset for land cover classification, buildings and roads are included in the urban class. There is no dominant class in OpenEarthMap and the class proportions are relatively balanced. The normalized histogram of the number of segments in a single image is shown in Figure 4. In terms of image size, LoveDA is the same (1024×1024 pixels) as OpenEarthMap, while DeepGlobe is larger (2448×2448 pixels). The histogram of OpenEarthMap has a very long tail, showing a much larger number of segments in each image of OpenEarthMap than the other datasets. The spatially detailed labeling of the OpeneEarthMap is reflected in the cross-dataset evaluation and the out-of-sample prediction results of trained models presented in Sections 5 and 6.

## 3 Land Cover Semantic Segmentation

### 3.1 Baselines

For the land cover semantic segmentation task, CNN-based and Transformer-based architectures were evaluated and compared on the OpenEarthMap dataset. More specifically, the chosen models are U-Net , U-NetFormer , FT-U-NetFormer , DeepLabV3 , HRNet , SETR , SegFormer , and UPerNet  with backbones of ViT , Twins , Swin Transformer , ConvNeXt , and K-Net .

### 3.2 Results

General results: The results obtained on the test set of OpenEarthMap are presented in Table 3. The main findings are discussed as follows: (1) U-Net with EfficientNet-B4 as backbone outperforms both U-Net with ResNet-34 and U-Net with VGG-11. The reason might be that EfficientNet-B4 is more effective for extracting relevant features, and to that effect, both high-level features and low-level spatial information are used for robust segmentation. (2) UPerNet with Swin-B and Twins, as well as SegFormer and K-Net perform better than DeepLabV3 and HRNet. This might be attributed to the strong modeling capabilities and dynamic feature aggregation of Swin-B, Twins, and MiT-B5. (3) U-NetFormer and FT-U-NetFormer share the top positions because both methods adopt a global–local Transformer block to construct global and local information in the decoder, and use advanced encoder (e.g., ResNeXt and Swin-B) to extract features. (4) UPerNet with ViT and ConvNeXt, along with SETR obtain worse results than other Transformer-based models. Two reasons might be that the hyperparameters (e.g., optimizer and learning rate) of these methods may need to be carefully tuned, and advanced data augmentation may be required for transfer learning from ImageNet to the OpenEarthMap dataset. In all, considering performance along with the number of parameters and FLOPs, U-Net-EfficientNet-B4, UPerNet-Swin-B, and FT-U-NetFormer are recommended.

Visualization:
Examples of segmentation results obtained from some selected methods are presented in Figure 5. The U-Net-EfficientNet-B4 and FT-U-NetFormer produce the best detailed visualization results. In the first row of Figure 5, DeeplabeV3 wrongly classified the water area of the dam as rangeland while other methods identified them. In the second row, U-Net-EfficientNet-B4, SegFormer and FT-U-NetFormer were able to identify the tiny roads in the top-right parts of the image.
Water and bareland classes respectively achieved the highest and the lowest accuracies in all methods. The boundaries of the buildings and the roads were difficult to identify properly because of disorganized layouts and varying sizes. Rangeland, agricultural land and trees are easy to confuse due to the similarities in their spectra. Roads were easily misclassified as developed space because parking lots and cover materials in some rural areas are quite similar.

Table 3: Semantic segmentation results of the baseline models on the test set of the OpenEarthMap dataset. The results are based on test-time augmentation (TTA), in particular flipping.

| Method | Backbone | IoU (%) Bareland | IoU (%) Rangeland | IoU (%) Developed | IoU (%) Road | IoU (%) Tree | IoU (%) Water | IoU (%) Agriculture | IoU (%) Building | mIoU (%) | Params (M) | FLOPs (G) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| U-Net | VGG-11 | 40.69 | 56.76 | 53.99 | 62.16 | 72.44 | 82.81 | 73.14 | 77.77 | 64.97 | 18.26 | 233.33 |
| U-Net | ResNet-34 | 40.35 | 57.75 | 54.92 | 62.87 | 72.65 | 82.24 | 74.06 | 78.58 | 65.43 | 24.44 | 126.68 |
| U-Net | EfficientNet-B4 | 50.63 | 58.17 | 56.27 | 64.83 | 73.20 | 86.02 | 76.28 | 80.20 | 68.20 | 20.30 | 45.47 |
| U-NetFormer | ResNeXt101 | 46.09 | 60.67 | 58.12 | 65.07 | 73.77 | 86.34 | 76.98 | 79.96 | 68.37 | 192.71 | 769.25 |
| FT-U-NetFormer | Swin-B | 50.19 | 60.84 | 57.58 | 65.85 | 73.33 | 87.44 | 77.50 | 80.29 | 69.13 | 95.98 | 498.37 |
| DeepLabV3 | ResNet-50 | 39.11 | 56.16 | 52.28 | 60.57 | 71.25 | 79.32 | 70.75 | 75.83 | 63.16 | 68.14 | 269.76 |
| HRNet | W48 | 39.71 | 55.50 | 53.49 | 59.22 | 71.10 | 79.03 | 71.38 | 75.12 | 63.07 | 65.89 | 94.06 |
| UPerNet | ViT | 34.39 | 54.45 | 50.64 | 54.57 | 69.73 | 79.24 | 66.22 | 74.92 | 60.52 | 144.17 | 395.07 |
| UPerNet | Swin-B | 44.52 | 58.98 | 54.78 | 63.43 | 72.20 | 83.71 | 72.97 | 78.11 | 66.09 | 59.94 | 236.08 |
| SegFormer | MiT-B5 | 36.84 | 57.94 | 53.53 | 63.60 | 70.51 | 80.11 | 72.21 | 77.35 | 64.01 | 81.97 | 51.86 |
| SETR PUP | ViT-L | 45.35 | 55.72 | 51.31 | 55.47 | 67.63 | 73.12 | 67.14 | 75.48 | 61.40 | 309.35 | 212.45 |
| UPerNet | Twins | 37.29 | 57.62 | 53.83 | 60.23 | 72.32 | 81.93 | 71.71 | 77.49 | 64.05 | 90.96 | 250.91 |
| UPerNet | ConvNeXt | 40.61 | 54.94 | 51.76 | 58.47 | 70.44 | 75.95 | 68.94 | 74.30 | 61.93 | 122.1 | 292.42 |
| K-Net | Swin-B | 44.02 | 57.81 | 54.85 | 62.91 | 71.76 | 85.18 | 73.41 | 78.91 | 66.11 | 246.97 | 419.51 |

Table 4: Lightweight models discovered on OpenEarthMap training set. FLOPs and FPS are measured on 1024×1024 input, and mIoU on the test set of OpenEarthMap.

| Method | Trial | Params (M) | FLOPs (G) | FPS (ms) | mIoU (%) No TTA | mIoU (%) TTA |
|---|---|---|---|---|---|---|
| SparseMask | 1st | 2.96 | 10.28 | 51.2 | 58.23 | 60.21 |
| SparseMask | 2nd | 3.10 | 10.39 | 52.2 | 58.06 | 60.00 |
| FasterSeg | 1st | 2.23 | 14.58 | 143.2 | 57.55 | 58.35 |
| FasterSeg | 2nd | 3.47 | 15.37 | 171.3 | 58.51 | 59.41 |

### 3.3 Neural Architecture Search

LoveDA , DeepGlobe , and other previous benchmarks  were experimented with only manually designed networks  for the semantic segmentation task. In contrast, we further experimented the OpenEarthMap dataset with two automated neural architecture search methods, SparseMask  and FasterSeg , by automatically searching for compact segmentation architectures. Such architectures might offer a useful baseline for research in the field of automated neural architecture search in remote sensing with OpenEarthMap.
Following the architecture search protocols in both methods (see the supplementary for more details), we searched for lightweight segmentation networks on the OpenEarthMap dataset. Four experiments were performed, two with each method, and the results are presented in Table 4. Both methods were able to discover compact networks, however, FasterSeg discovered the lightest-weight network. The networks discovered by SparseMask have less computational complexity but with low inference speed. Whereas FasterSeg networks have high computation cost and high inference speed. For real-time mapping (no TTA), FasterSeg might serve as a baseline for the OpenEarthMap dataset. For non real-time mapping (where TTA is used), SparseMask might be adopted as a baseline. Compared to the manually designed baseline models presented in Table 3, the lightweight discovered networks (<4M params) competed with UPerNet-ViT (144.17M params) and trailed behind FT-U-NetFormer (95.98M params) by approximately 9% accuracy rate.

### 3.4 Human Annotation vs Machine Prediction

As mentioned in Section 2.2, 200 images were labeled twice by different people. The remaining 4800 images were used to train UPerNet with Swin-B to compare the quality of human labeling with the results from the machine. To effectively investigate the comparison, the number of training images was varied from 10% to 100%; the results are shown in Figure 6. It can be seen that with 50% of the training images, the machine attains almost the same level of human annotation and larger training percentages improve the accuracy (see Figure 6). For human annotation, the challenging classes include bareland, rangeland, and tree. For bareland, rangeland, developed space, and tree classes, 50%, 30%, 50%, and 10% of the training set, respectively, yielded better results than the ones of human annotation (see Figure 6). The challenging class for the machine is agriculture land, where it trails behind human annotation by 2.3%. Regarding road, water, and building classes, with 100% of the training images, the machine slightly (<0.34%) trails behind the human annotation.

### 3.5 Learning from Limited Labels

We also investigated the performance of CNN-based (U-Net-EfficientNet-B4) and Transformer-based (SegFormer, UPerNet-Swin-B and K-Net) models on limited training samples. Table 5 presents the results of using only 10% of the OpenEarthMap training set to train the models. It is apparent from Table 5 that U-Net-EfficientNet-B4 outperforms all three Vision Transformer-based methods in all the class-specific IoUs by about 6-15%.The main reason is that the representation capacity of ViTs typically lacks the inductive bias in CNNs. Therefore, ViTs require more training data than CNNs . We believe that Vision Transformers with small-sized data  or limited labels  is an interesting topic that requires further study. Moreover, data augmentation, regularization, and tuning of hyper-parameters still need to be explored when training on limited training data .

## 4 Unsupervised Domain Adaptation

### 4.1 Baselines

For the unsupervised domain adaptation task, a metric-based method (MCD ), adversarial training methods including AdaptSeg , category-level adversarial network (CLAN) , TransNorm , and fine-grained adversarial learning framework for domain adaptive (FADA) ), as well as self-training methods including pyramid curriculum DA (PyCDA) , class-balanced self-training (CBST) , instance adaptive self-training (IAST) , and DAFormer  are adopted. DAFormer is based on SegFormer and the others are based on DeepLabV2.

### 4.2 Results

Table 5: Semantic segmentation results of selected baseline models trained on only 10% of OpenEarthMap training set.

|  | Bare | Range | Dev | Road | Tree | Water | Agri | Building | mIoU |
|---|---|---|---|---|---|---|---|---|---|
| U-Net-EfficientNet-B4 | 32.62 | 52.43 | 49.77 | 58.47 | 69.26 | 74.39 | 70.16 | 74.35 | 60.18 |
| SegFormer | 16.15 | 44.08 | 45.88 | 51.39 | 65.72 | 61.42 | 58.54 | 69.71 | 51.61 |
| UPerNet-Swin-B | 18.32 | 47.82 | 48.2 | 53.46 | 66.89 | 59.62 | 55.22 | 69.55 | 52.39 |
| K-Net | 18.62 | 50.26 | 48.93 | 55.22 | 66.45 | 60.76 | 62.06 | 72.33 | 54.33 |

Table 6: Unsupervised domain adaptation results obtained on the test set of 24 regions in the OpenEarthMap dataset.

| DeeplabV2-based | Type DeeplabV2-based | IoU (%) Bare DeeplabV2-based | IoU (%) Range DeeplabV2-based | IoU (%) Dev DeeplabV2-based | IoU (%) Road DeeplabV2-based | IoU (%) Tree DeeplabV2-based | IoU (%) Water DeeplabV2-based | IoU (%) Agri DeeplabV2-based | IoU (%) Build DeeplabV2-based | mIoU (%) DeeplabV2-based |
|---|---|---|---|---|---|---|---|---|---|---|
| Oracle | — | 37.06 | 43.65 | 38.03 | 43.12 | 61.61 | 73.89 | 75.90 | 63.93 | 54.65 |
| Source only | — | 26.86 | 42.14 | 36.48 | 42.03 | 58.58 | 61.35 | 70.77 | 61.87 | 50.01 |
| MCD | — | 16.77 | 41.55 | 35.89 | 44.24 | 56.15 | 57.84 | 62.57 | 63.83 | 47.36 |
| AdaptSeg | AT | 28.77 | 41.47 | 36.09 | 45.16 | 46.65 | 34.48 | 68.47 | 63.74 | 45.60 |
| FADA | AT | 26.29 | 37.91 | 34.91 | 37.13 | 54.19 | 40.68 | 65.36 | 58.32 | 44.35 |
| CLAN | AT | 22.90 | 42.25 | 39.49 | 44.12 | 58.98 | 58.99 | 59.51 | 64.53 | 48.85 |
| TransNorm | AT | 27.54 | 45.13 | 37.99 | 45.56 | 57.06 | 63.84 | 66.26 | 64.71 | 51.01 |
| PyCDA | ST | 21.95 | 32.33 | 22.89 | 34.81 | 44.95 | 34.16 | 56.74 | 55.31 | 37.89 |
| CBST | ST | 29.64 | 43.79 | 37.99 | 49.19 | 57.33 | 60.75 | 71.93 | 65.46 | 52.01 |
| IAST | ST | 33.68 | 43.64 | 37.03 | 45.16 | 59.61 | 72.08 | 74.72 | 61.77 | 53.46 |
| SegFormer-based | SegFormer-based | SegFormer-based | SegFormer-based | SegFormer-based | SegFormer-based | SegFormer-based | SegFormer-based | SegFormer-based | SegFormer-based | SegFormer-based |
| Oracle | — | 43.14 | 53.02 | 51.50 | 61.13 | 68.06 | 81.89 | 81.38 | 79.81 | 64.99 |
| Source only | — | 28.37 | 48.96 | 46.49 | 54.05 | 67.62 | 75.32 | 77.93 | 75.79 | 59.32 |
| DAFormer | ST | 37.16 | 51.07 | 50.36 | 58.07 | 68.3 4 | 78.39 | 78.08 | 77.30 | 62.35 |

Regional-level UDA: We investigated the regional-level domain gap since different regions in the same continent might suffer from a distribution shift. The results obtained on the test set of 24 regions of OpenEarthMap are presented in Table 6. In general, the Oracle settings obtained the best results. Due to the regional domain gap, the source-only settings yielded the lowest accuracy. The results of source-only SegFormer are significantly better than those of source-only DeepLabV2. Compared to manufactured classes (i.e., building and road), the accuracies of natural classes (i.e., water and bareland) decreased significantly. With the exception of TransNorm, the adversarial training methods did not perform well on this task due to the diversity in the OpenEarthMap dataset. TransNorm slightly improved the performance because the source and the target images have distinct spectral statistics since they were taken from different sensors and regions. The class imbalance problem is addressed using pseudo-label creation via the CBST and IAST techniques, resulting in higher performance. Due to better domain generalization of SegFormer and effective training strategy in self-training, DAFormer obtained the best mIoU of 62.35%. Visual examples of the UDA results are presented in Figure 7.
In the first row of Figure 7, source-only DeepLabV2 can barely identify the water area (top-right) and the roads (bottom-right). IAST and CBST performance improves for water but they lose the ability to recognize the roads. DAFormer performs very well in the two complex areas. In the second row, DAFormer shows better visualization results in the small water area (top-right) and the boundaries of roads and buildings than the other UDA methods.

Continent-wise UDA:

We also investigated the continent-wise domain gap on the OpenEarthMap dataset using U-Net-EfficientNet-B4, SegFormer, and DAFormer. The results are presented in Figure 8. Compared to the UDA settings (e.g., GTA5\rightarrowCityscapes with similar content and different style) in computer vision and previous settings in remote sensing (e.g., urban\rightarrowrural in LoveDA), UDA on continent-wise has larger content and style gaps. The limited data of Oceania (OC) led to the lowest transferred results when OC is treated as the source domain. In contrast, the performance with OC as the target domain is better than other settings. Expect OC, U-Net-EfficientNet-B4 and SegFormer indicated two minor domain gaps: Europe (EU)-to-North America (NA) and Asia (AS)-to-NA. The most prominent domain gap revealed by EfficientNet-B4 and SegFormer is Africa (AF)-to-EU and NA-to-AF, respectively. For challenging UDA settings, SegFormer is generally better than U-Net-EfficientNet-B4 (26 out of 30), which is the opposite of the results in the semantic segmentation (see Table 3) and the regional UDA setting (see Table 6). DAFormer improved the results compared to SegFormer in many cases (20 out of 30). DAFormer on AF-to-OC and NA-to-OC achieved significantly poor results due to the collapsed construction of pseudo labels in the limited data of OC. Thus, challenging continent-wise UDA settings are worth exploring and possible solutions may include the extension of DAFormer or new UDA method with U-Net-EfficientNet-B4.

## 5 Cross-Dataset Evaluation

In this section, we evaluate the advantage of using the OpenEarthMap dataset as a starting point (fine-tuning) in the semantic segmentation task over other open-source land cover mapping datasets. Here we compare OpenEarthMap with LoveDA  and DeepGlobe . We adopted the same U-Net model with an EfficientNet-B4 as a backbone listed in Table 3 and trained from scratch on the three datasets using similar training settings as Section 3.2. Then, we fine-tuned the OpenEarthMap and the LoveDA pre-trained models on the DeepGlobe dataset. Similarly, the OpenEarthMap and the DeepGlobe pre-trained models were fine-tuned on the LoveDA dataset. All the experiments were run threefold; we report the mean and the standard deviation segmentation accuracy for 20 epochs. As presented in Figure 9, the results indicate that using a model that is pre-trained on OpenEarthMap as a starting point could yield better performance than models pre-trained on LoveDA and DeepGlobe. For example, when fine-tuned on the DeepGlobe dataset, the initial IoU score of the OpenEarthMap pre-trained model is about 4% higher than the fully-trained model on DeepGloble (see Figure 9). Although the OpenEarthMap pre-trained model is slightly lower than the LoveDA pre-trained one in early epochs, OpenEarthMap increasingly outperforms both models as the number of epochs increases. Furthermore, when fine-tuned on the LoveDA dataset, the OpenEarthMap pre-trained model attains a more than 20% increase in the initial IoU score, and its performance remains higher when the number of epochs increases (see Figure 9).

## 6 Demonstration on Out-of-Sample Imagery

To further investigate the generalization performance of a model trained on OpenEarthMap, we created land cover classification maps from out-of-sample imagery (i.e., images that are not included in OpenEarthMap). See the supplementary for more results. Here we present a map created from an NAIP  image resampled at 0.5m GSD. A Chesapeake Bay land cover map  was used as reference to evaluate performance. The Chesapeake Bay land cover map consists of 13 classes. To fairly compare the mapping results of the Chesapeake Bay land cover tool with those produced by U-Net models trained on OpenEarthMap and LoveDA, we adopted six common classes (bareland, other, road, tree, water, and building) among the datasets and performed quantitative evaluation. Table 7 shows the accuracy of the land cover mapping for an area of approximately 15km× 28km in US, spanning from Washington, DC to Maryland. The IoUs from OpenEarthMap model are significantly higher than those from LoveDA, and the scores are high enough for practical mapping except bareland. The accuracy of bareland is low due to inconsistency in class definitions. For example, in the Chesapeake Bay land cover map, a construction site is labeled as bareland, while OpenEarthMap labels the same area as developed space. Figure S11 shows a visual example of the mapping results. Note that unlike the quantitative evaluation in Table 7, the vegetation classes (low vegetation, agriculture land, and rangeland) that differ among the datasets are visualized in different colors. The OpenEarthMap model result is similar to the Chesapeake Bay land cover map in both classification and resolution, and achieved very fine spatial segmentation compared to the LoveDA model. This demonstrates the advantage of OpenEarthMap over LoveDA and how finely OpenEarthMap’s annotations are spatially detailed.

Table 7: Generalization performance of models trained on OpenEarthMap and LoveDA, and evaluated with IoU (%) using the Chesapeake Bay high-resolution land cover map.

| Dataset | Bare | Other | Road | Tree | Water | Build | mIoU |
|---|---|---|---|---|---|---|---|
| OpenEarthMap | 9.29 | 58.27 | 49.29 | 75.72 | 85.46 | 63.44 | 56.91 |
| LoveDA | 3.07 | 40.14 | 37.71 | 69.34 | 80.12 | 45.85 | 46.04 |

## 7 Conclusion and Societal Impacts

The existing benchmarks for land cover classification at sub-meter resolution lack regional diversity and annotation quality. To address this problem, we introduce OpenEarthMap, a benchmark dataset, for global high-resolution land cover mapping.
The diversity of the dataset is shown in the coverage of 97 regions from 44 countries across 6 continents, while its finely detailed annotations are reflected in the generalization of the feature space.
To demonstrate the practical usefulness of OpenEarthMap, we perform baseline experiments with several state-of-the-art models for semantic segmentation and UDA tasks, and create land cover maps for out-of-sample imagery to show that models trained on OpenEarthMap can adapt and generalize across the globe. We also demonstrate the challenges of the continent-wise domain gap and limited data training. We experiment NAS-based lightweight models for mapping with resource-limited devices. Further technical development is needed to improve the performance in continent-wise domain adaptation, limited training data, and lightweight models on OpenEarthMap for worldwide evaluation. The dataset will be made publicly available for other researchers to build on it and create new practical tasks.

Societal Impacts: OpenEarthMap models could enable automated mapping of any location on Earth, which can support decision making in disaster response, environmental conservation, and urban planning. However, such models will make it easy for anyone to access map information related to national security as well as privacy if sub-meter resolution images are available. Appropriate data analysis ethics and data policies are required to avoid security and privacy breaches.

In this supplementary, we provide a detailed description of the land cover classes of the OpenEarthMap dataset. We also present a brief overview of the baseline methods that were experimented on the OpenEarthMap dataset for the semantic segmentation and unsupervised domain adaptation tasks. The training settings and more experimental results on the semantic segmentation and the unsupervised domain adaptation tasks are presented. Furthermore, we provide more land cover mapping results that were created from out-of-sample images (i.e., images not included in OpenEarthMap) to further demonstrate the generalization of the OpenEarthMap feature space. The attribution of all source data is summarized at the end.

## S1 Land Cover Classes

Using the Anderson classification  as a starting point, we subdivided the urban class into three classes: building, road, and developed space, which are visually interpretable in high-resolution images at a sub-meter level of ground sampling distance (GSD). The definitions of 8 classes in OpenEarthMap are summarized as follows.

- Bareland includes natural areas covered by sand or rocks without vegetation, and other accumulations of earthen materials.
- Rangeland includes areas dominated by herbaceous vegetation or bushes that are not cultivated or grazed, as well as grass and shrubs in gardens, parks, and golf courses.
- Developed space includes areas such as sidewalks, pavements, footpaths, parking lots, and construction sites as well as artificial grass areas search as tennis courts, baseball and football fields, etc. A lane in-between parking lots is considered as a road. The materials include asphalt, concrete, stones, bricks, and tiles. Compacted soil is also labeled as developed space.
- Road includes lanes, streets, railways, airport runways, and highway/motorway for vehicles (e.g., trucks, cars, motorbikes, trains, and airplanes) excluding bicycles. The materials of roads include asphalt, concrete, and soil.
- Tree includes individual trees and a group of trees that are identified from their shapes (shadow) and height.
- Water includes water bodies (e.g., rivers, streams, lakes, sea, ponds, dams) and swimming pools.
- Agriculture land includes areas used for producing crops (e.g., rice, wheat corn, soybeans, vegetables, tobacco, and cotton), perennial woody crops (e.g., orchards and vineyards), and non-native vegetation for grazing.
- Building includes residential, commercial, and industrial buildings.

Figure S1 shows a t-SNE 2D plot of the 97 regions using class proportions in the OpenEarthMap dataset. As can be seen in the bar graphs of 12 representative regions, the class proportions in the different regions are diverse.

## S2 Land Cover Semantic Segmentation

### S2.1 Brief Overview of the Baselines

The land cover semantic segmentation baseline networks that were experimented on the OpenEarthMap dataset are CNN-based (U-Net , DeepLabV3 , HRNet , K-Net , and ConvNeXt ) and Transformer-based (U-NetFormer , FT-U-NetFormer , SETR , SegFormer , UPerNet  with the backbones of ViT , Twins , and Swin Transformer ) architectures. U-Net uses an encoder-decoder structure to extract objects and image context at different scales.
U-Net models with VGG-11, ResNet-34, and EfficientNet-B4 as backbones were adopted. DeepLabV3  uses a dilation hyperparameter of convolutional layers to develop atrous spatial pyramid pooling for robust object segmentation through many scales. HRNet builds high-resolution representations by continually executing multi-scale fusions across parallel convolutions. We employed an HRNet with W48 as a backbone. K-Net  separates instances and semantic categories uniformly with a number of learnable kernels. The kernels conduct convolution on the image features to provide segmentation predictions. ConvNeXt  is a pure ConvNet model constructed entirely from standard ConvNet modules. UPerNet with a backbone of ConvNeXt-B was used. The U-NetFormer  selects the advanced ResNext101 as the encoder
and develops an efficient global–local attention mechanism to model both global and local information in the
decoder. FT-U-NetFormer  replaces the CNN encoder with the
Swin Transformer (Swin-B).
SETR  interprets an input image as a sequence of patches represented by a learned patch embedding, then, modifies the sequence using a global self-attention module for discriminative feature representation learning. A SETR PUP with a backbone of ViT-L was used. SegFormer  unifies transformers with lightweight multilayer perceptron decoders without considering positional encoding. A MiT-B5 encoder was used as a backbone for SegFormer. Swin Transformer  creates hierarchical feature maps by merging image patches into deeper layers. Twins  uses a spatially separable attention mechanism comprising of locally-grouped self-attention and global sub-sampled attention.

Table S1: Performance of ImageNet pre-trained model with different optimizers.

| Model | Pre-trained on | Optimizer | mIoU |
|---|---|---|---|
| UPerNet-Swin-B | ImageNet | SGD | 62.15 |
| UPerNet-Swin-B | ImageNet | AadmW | 66.09 |
| UPerNet-Swin-B | None | SGD | 62.32 |
| UPerNet-Swin-B | None | AadmW | 66.13 |

Table S2: The results of using different input patch sizes and different loss functions with UPerNet-Swin-B.

(a) Input patch size

| Patch size | mIoU |
|---|---|
| 512 × 512 | 66.09 |
| 620 × 620 | 66.14 |
| 768 × 768 | 66.17 |
| 1024 × 1024 | 67.02 |

(b) Loss functions

| Function | mIoU |
|---|---|
| CE | 66.09 |
| CE+Lovasz | 66.21 |
| CE+Focal | 65.89 |
| CE+Lovasz+Focal | 66.38 |

Table S3: Compact segmentation models discovered on OpenEarthMap training set with SparseMask and FasterSeg. The class IoUs and the mIoU are calculated on the test set of OpenEarthMap with TTA applied.

| Method | Trial | IoU (%) Bareland | IoU (%) Rangeland | IoU (%) Developed | IoU (%) Road | IoU (%) Tree | IoU (%) Water | IoU (%) Agriculture | IoU (%) Building | mIoU (%) | Params (M) | FLOPs (G) | FPS (ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SparseMask | 1st | 47.00 | 53.42 | 46.40 | 46.94 | 66.98 | 79.02 | 72.64 | 69.25 | 60.21 | 2.96 | 10.28 | 25.9 |
| SparseMask | 2nd | 45.96 | 53.01 | 46.71 | 47.26 | 67.12 | 78.81 | 71.88 | 69.27 | 60.00 | 3.10 | 10.39 | 26.4 |
| FasterSeg | 1st | 34.04 | 51.40 | 44.97 | 55.82 | 66.58 | 74.50 | 70.33 | 69.14 | 58.35 | 2.23 | 14.58 | 74.8 |
| FasterSeg | 2nd | 35.78 | 52.03 | 46.32 | 56.97 | 67.20 | 75.76 | 70.70 | 70.55 | 59.41 | 3.47 | 15.37 | 89.5 |

Table S4: Compact segmentation models discovered on OpenEarthMap training set with SparseMask and FasterSeg. The class IoUs and the mIoU are calculated on the test set of OpenEarthMap without TTA applied.

| Method | Trial | IoU (%) Bareland | IoU (%) Rangeland | IoU (%) Developed | IoU (%) Road | IoU (%) Tree | IoU (%) Water | IoU (%) Agriculture | IoU (%) Building | mIoU (%) | Params (M) | FLOPs (G) | FPS (ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SparseMask | 1st | 46.15 | 51.88 | 44.01 | 43.64 | 65.20 | 77.41 | 71.47 | 66.10 | 58.23 | 2.96 | 10.28 | 51.2 |
| SparseMask | 2nd | 44.78 | 51.56 | 44.34 | 43.95 | 65.44 | 77.34 | 70.98 | 66.09 | 58.06 | 3.10 | 10.39 | 57.2 |
| FasterSeg | 1st | 33.52 | 50.60 | 43.93 | 54.74 | 65.98 | 73.55 | 69.73 | 68.36 | 57.55 | 2.23 | 14.58 | 143.2 |
| FasterSeg | 2nd | 34.50 | 51.27 | 45.27 | 55.94 | 66.61 | 74.71 | 70.05 | 69.73 | 58.51 | 3.47 | 15.37 | 171.3 |

### S2.2 Experimental Details

All the baselines we used for the experiments are PyTorch-based. The U-Net-based architectures are adopted from Yakubovskiy  and Wang et al. , and the other architectures are from MMsegmentation . The networks were trained on a single NVIDIA GPU DGX-1/DGX-2 with 16/32GB of RAM. The number of epochs was set to 200, and a batch size of 8 with an image input size of 512×512 randomly cropped was employed. The cross-entropy (CE) loss was used in training all the networks. For the U-Net-based architectures, we used AdamW optimizer  with a learning rate of 1× 10^-4 and weight decay of 1× 10^-6. For the MMsegmentation-based architectures, we used the default settings of each method. We adopted stochastic gradient descent (SGD) optimizer with a learning rate of 1× 10^-3, weight decay of 5× 10^-4, and momentum of 0.9 for the DeeplabV3 and HRNet networks. The rest of the networks used AdamW optimizer with a learning rate set as 6× 10^-5, weight decay as 0.01, and betas parameters as 0.9 and 0.999. A polynomial learning rate decay with a factor of 1.0 and an initial linear warm-up of 1500 iterations was used. The backbones in all the networks were pre-trained on the ImageNet dataset. No data augmentation was applied during training for all networks. Following previous works, we used mIoU to assess the performance of all models. All results are based on test-time augmentation (TTA) with flipping operations.

### S2.3 Results

Visualization:
More visual examples of segmentation results obtained from some selected baseline methods are presented in Figure S2.
In the first row (Rotterdam), DeepLabV3 failed to identify the entire stretch of road. In the second row (San Tiago), the entire bareland and the small developed space on top of the bareland were identified by FT-U-NetFormer and SegFormer. U-Net-EfficientNet-B4, FT-U-NetFormer and SegFormer were able to identify the bareland that stretches from along the river (third row), but DeepLabV3, UPerNet-Swin-B, and K-Net failed to identify it. Compared to DeepLabV3 and K-Net, U-Net-EfficientNet-B4, DeepLabV3, and FT-U-NetFormer did recognize most parts of the water body in Viru (fourth row). UPerNet-Swin-B and DeeplabV3 classified the water body in Viru as agricultural land, rangeland, and developed space.

Ablation study:
We conducted an ablation study to examine the effects of ImageNet pre-training, optimizers, image size, and loss functions on the OpenEarthMap dataset using a UPerNet-Swin-B network. We employed two different optimizers (AadmW and SGD), three loss functions (CE, Lovasz, and Focal), and four different patch sizes. As shown in Table S1, the model that was not pre-trained on ImageNet performed better than the one pre-trained on ImageNet. In both cases, AdamW optimizer attains better results. Table 2(b) shows the results of using different patch sizes and different loss functions for training UPerNet-Swin-B. A larger patch size tends to achieve better performance. The combination of all three loss functions (CE, Lovasz, and Focal) can improve the performance of UPerNet-Swin-B.

### S2.4 Neural Architecture Search Methods

The two automated neural architecture search methods, SparseMask  and FasterSeg , which we adopted were particularly proposed for compact architecture search for semantic segmentation tasks in computer vision. Both methods employed a gradient-based search strategy similar to the one used in DARTS . Whereas SparseMask used a pruning technique to compress the searched architectures, teacher-student co-searching (knowledge distillation technique) was used in FasterSeg. Following the architecture search protocol in both methods, we conducted four experiments, two with each method, by searching for lightweight architectures on the OpenEarthMap dataset. All the experiments we performed on a single NVIDIA Tesla P100 with 16GB memory. It took about 0.8 GPU days and 2 GPU days to perform the architecture search with SparseMask and FasterSeg, respectively. The architectures discovered with both methods were trained from scratch using the same training protocol adopted in  and  with the exception of setting the number of epochs to 450. We measured the class-specific IoUs and mIoU using a single-scale input with TTA (see Table  S3) and without TTA (see Table  S4) of flipping operations applied to the test set of the OpenEarthMap dataset. The FPS and the FLOPs were calculated with a single image of 1024×1024 pixels as an input. The inference speed was calculated using the settings in FasterSeg. Table  S3 and Table S4 show the detail class-specific IoUs along with the mIoUs that are presented in the paper.

## S3 Unsupevised Domain Adaptation

### S3.1 Brief Overview of the Baselines

We adopted a metric-based method (MCD ), adversarial training methods (AdaptSeg , category-level adversarial network (CLAN) , TransNorm , and fine-grained adversarial learning framework for domain adaptive (FADA) ), and self-training methods (pyramid curriculum DA (PyCDA) , class-balanced self-training (CBST) , instance adaptive self-training (IAST) , and DAFormer ) for the unsupervised domain adaptation task. DAFormer is a transformer-based model, and the others are based on DeepLabV2. The adversarial training methods seek to match the distributions of the source and target domains from input-feature-output or a patch level in a generative adversarial network. AdaptSeg  uses adversarial learning in the output space and a multi-level adversarial network to effectively perform output space domain adaptation at different feature levels. CLAN  aligns the classes with an adaptive adversarial loss. TransNorm  uses an end-to-end trainable layer to make networks more transferable across domains. FADA  uses a fine-grained adversarial learning framework by aligning the class-level features. Self-learning methods generate the target domain’s pseudo labels, retrain the model and repeat the procedure. PyCDA  observes the target properties and fuses multi-scale features. CBST  and IAST  aim at selecting balanced samples to improve the quality of pseudo labels. DAFormer  constructs a transformer encoder and a multilevel context-aware feature fusion decoder by adopting three effective training strategies: rare class sampling, ImageNet Feature Distance, and a learning rate warmup.

Table S5: Comparing source-only and oracle training for different networks on the 24 regions test set of OpenEarthMap.

| Model | mIoU (%) Source-only | mIoU (%) Oracle |
|---|---|---|
| U-Net-EfficientNet-B4 | 63.17 | 64.09 |
| DeepLabV2 | 50.01 | 54.65 |
| DeepLabV3 | 55.27 | 59.83 |
| HRNet | 56.25 | 60.02 |
| SegFormer | 58.25 | 64.76 |
| UPerNet-Swin-B | 52.35 | 61.82 |
| K-Net | 57.21 | 64.12 |

### S3.2 Experimental Details

For the DeepLabV2-based methods, we adopted the architectures in Wang et al.  and kept the default setting. We used the following training settings (batch size of 8 with image input size of 512×512 randomly cropped) in the semantic segmentation task for all the DeepLabV2-based methods and the DAFormer.
DeepLabV2 with ResNet50 was used as an extractor, and a discriminator was constructed using fully convolutional layers.
The classification and the discriminator learning rates for the adversarial training methods were set to 5× 10^-3 and 10^-4, respectively. Adam optimizer was used in the discriminator with momentum of 0.9 and 0.99. We adopted the default pseudo-generation hyper-parameters in CBST and IAST, and set the classification learning rate to 10^-2. All the networks were trained for 40K steps in two stages. In the first stage, the models were trained only on the source images for 8K steps for initialization. In the second stage, the pseudo-labels were then updated every 2K steps for the remaining training process. For the DAFormer, an MiT-B5 encoder was adopted with AdamW. Other hyper-parameters remained the same as in the original literature .

### S3.3 Results

Visualization: More visual examples of the UDA results are presented in Figure S3.
In the first row (Palu), the source-only DeepLabV2 can barely identify the tree (bottom-left) and developed space (center-left). These areas were classified as bareland and water. CBST and IAST also did not perform well in these areas. Source-only SegFormer and DAFormer slightly improved their performance in these areas. In the second row (Dowa), source-only DeepLabV2 could not recognize the tiny road and small buildings. IAST and CBST performed better on the road, but they cloud not recognize the small buildings. DAFormer performs exceptionally well in those two areas. In the third row (Dusseldorf), DAFormer could identify the long and tiny road (bottom), and the other methods only recognized some parts of the road.
The IAST did identify the small water area (top-left) in Vienna (fourth row), and the other methods classified it as building.

Comparison of network architectures:
To further evaluate the suitability of the networks for the UDA task, we performed several experiments with source-only and oracle training for different models and provided their mIoU results in Table. S5. The classical DeepLabV2 yielded the worst results in both source-only and oracle. UPerNet-Swin-B was slightly better than DeepLabV2 in the source-only setting. SegFormer obtained the best oracle performance, and U-Net-EfficientNet-B4 outperformed SegFormer on the source-only setting. Generally, U-Net-EfficientNet-B4, SegFormer, and K-Net shared the top positions in both source-only and oracle settings. These networks are recommended to be further investigated for the development of UDA methods on the OpenEarthMap dataset.

Continent-wise UDA:
Visual comparison of continent-wise UDA results of source-only SegFormer, Oracle and DAFormer are shown in Figure S4. Eight combinations of source and target domains are provided. Here, we denote Africa, Asia, Europe, North America, South America, and Oceania as AF, AS, EU, NA, SA, and OC, respectively. For AF\rightarrowAS, AS\rightarrowEU, and AF\rightarrowEU, DAFormer significantly achieved better results on agriculture land when compared to source-only SegFormer. DAFormer also identified the water in EU\rightarrowNA, and the small buildings and the tiny roads in SA\rightarrowAF and AF\rightarrowNA. The class-specific IoUs and mIoUs obtained from source-only U-Net-EfficientNet-B4, source-only SegFormer, and DAFormer are presented in Figure S8, Figure S8, and Figure S8, respectively. For most classes, when OC is considered as the source domain, the transferred result is worst due to the limited number of images in OC. However, when OC is treated as the target domain the performance is better than other settings. With the exception of OC, building is the easiest transferred class, which U-Net-EfficientNet-B4 achieved IoUs range of 63.4 to 76.8 and SegFormer achieved a range of 64.3 to 76.3. The most challenging transferred class is bareland. The U-Net-EfficientNet-B4 and the SegFormer attained IoUs range of 4.3 to 32.5 and 4.1 to 32.7, respectively. In the order of easiest to challenging class is building, tree, road, rangeland, developed space,water, agriculture land, and bareland. The performance change from SegFormer to DAFormer is shown in Figure S8. Red indicates an improvement whereas blue depicts a decrease in results. In Figure S8, one can clearly see that DAFormer improved the results in the challenging classes (e.g., bareland and water).

## S4 Mapping for Out-of-Sample Images

Figure S11 shows visual comparisons of the Chesapeake Bay land cover map with those generated by U-Net-EfficientNet-B4 models trained on OpenEarthMap, LoveDA, DeepGlobe, and DynamicEarthNet with the same implementation details. The results obtained by the OpenEarthMap model demonstrate fine spatial details and semantically consistent mapping with the Chesapeake Bay land cover map. Note that the maps of the DynamicEarthNet model were obtained with the original 1m GSD because they yielded better results than those processed with 3m GSD. See Figure S11 for a comparison of mapping results with the DynamicEarthNet model using images at different GSDs (i.e., 0.5cm, 1m, and 3m) for inference.

Furthermore, we demonstrate visual results of land cover mapping for out-of-sample images from France (MiniFrance ), China (LoveDA ), Ecuador (SIGTIERRAS (1 http://www.sigtierras.gob.ec/)), and Tanzania (Zanzibar Mapping Initiative (ZMI) (2 http://www.zanzibarmapping.org/)) in Figures S11, S14, S14, and S14, respectively. These land cover maps were obtained by a U-Net-EfficientNet-B4 trained on the OpenEarthMap dataset. One can observe that the results are at a reasonably high resolution. Considering the fact that these images are not included in the OpenEarthMap dataset, the results further support the generalization capability of the OpenEarthMap model.

## S5 Attribution of Source Data

Table S6 summarizes attribution of source data for 97 regions in OpenEarthMap. Our label data are provided under the same license as the original RGB images, which varies with each source dataset. Label data for regions where the original RGB images are in the public domain or where the license is not explicitly stated are licensed under a Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License.

Table S6: Attribution of source data of the 97 regions in OpenEarthMap.

| Region | Country | Source data | URL | Provider | License |
|---|---|---|---|---|---|
| Christchurch | New Zealand | AIRS | https://www.airs-dataset.com/ | Land Information of New Zealand | CC BY 4.0 |
| Aachen | Germany | GeoNRW | https://www.opengeodata.nrw.de/produkte/ | German state North Rhine-Westphalia | DL-DE-BY-2.0 |
| Bielefeld | Germany | GeoNRW | https://www.opengeodata.nrw.de/produkte/ | German state North Rhine-Westphalia | DL-DE-BY-2.0 |
| Dortmunt | Germany | GeoNRW | https://www.opengeodata.nrw.de/produkte/ | German state North Rhine-Westphalia | DL-DE-BY-2.0 |
| Dusseldorf | Germany | GeoNRW | https://www.opengeodata.nrw.de/produkte/ | German state North Rhine-Westphalia | DL-DE-BY-2.0 |
| Koeln | Germany | GeoNRW | https://www.opengeodata.nrw.de/produkte/ | German state North Rhine-Westphalia | DL-DE-BY-2.0 |
| Muenster | Germany | GeoNRW | https://www.opengeodata.nrw.de/produkte/ | German state North Rhine-Westphalia | DL-DE-BY-2.0 |
| Chisinau | Moldova | HTCD | https://map.openaerialmap.org | Lightcyphers | CC BY 4.0 |
| Tyrol | Austria | Inria | https://project.inria.fr/aerialimagelabeling/ | Tyrol | Public domain |
| Vienna | Austria | Inria | https://project.inria.fr/aerialimagelabeling/ | Vienna | Public domain |
| Austin | USA | Inria | https://project.inria.fr/aerialimagelabeling/ | USGS | Public domain |
| Chicago | USA | Inria | https://project.inria.fr/aerialimagelabeling/ | USGS | Public domain |
| Kitsap | USA | Inria | https://project.inria.fr/aerialimagelabeling/ | USGS | Public domain |
| Dolnoslaskie | Poland | Landcover.ai | https://landcover.ai.linuxpolska.com/ | Head Office of Geodesy and Cartography | CC BY-NC-SA 4.0 |
| Kujawsko-pomorskie | Poland | Landcover.ai | https://landcover.ai.linuxpolska.com/ | Head Office of Geodesy and Cartography | CC BY-NC-SA 4.0 |
| Lodzkie | Poland | Landcover.ai | https://landcover.ai.linuxpolska.com/ | Head Office of Geodesy and Cartography | CC BY-NC-SA 4.0 |
| Lubuskie | Poland | Landcover.ai | https://landcover.ai.linuxpolska.com/ | Head Office of Geodesy and Cartography | CC BY-NC-SA 4.0 |
| Malopolskie | Poland | Landcover.ai | https://landcover.ai.linuxpolska.com/ | Head Office of Geodesy and Cartography | CC BY-NC-SA 4.0 |
| Mazowieckie | Poland | Landcover.ai | https://landcover.ai.linuxpolska.com/ | Head Office of Geodesy and Cartography | CC BY-NC-SA 4.0 |
| Podkarpackie | Poland | Landcover.ai | https://landcover.ai.linuxpolska.com/ | Head Office of Geodesy and Cartography | CC BY-NC-SA 4.0 |
| Podlaskie | Poland | Landcover.ai | https://landcover.ai.linuxpolska.com/ | Head Office of Geodesy and Cartography | CC BY-NC-SA 4.0 |
| Pomorskie | Poland | Landcover.ai | https://landcover.ai.linuxpolska.com/ | Head Office of Geodesy and Cartography | CC BY-NC-SA 4.0 |
| Slaskie | Poland | Landcover.ai | https://landcover.ai.linuxpolska.com/ | Head Office of Geodesy and Cartography | CC BY-NC-SA 4.0 |
| Swietokrzyskie | Poland | Landcover.ai | https://landcover.ai.linuxpolska.com/ | Head Office of Geodesy and Cartography | CC BY-NC-SA 4.0 |
| Warminsko-mazurskie | Poland | Landcover.ai | https://landcover.ai.linuxpolska.com/ | Head Office of Geodesy and Cartography | CC BY-NC-SA 4.0 |
| Wielkopolskie | Poland | Landcover.ai | https://landcover.ai.linuxpolska.com/ | Head Office of Geodesy and Cartography | CC BY-NC-SA 4.0 |
| Zachodniopomorskie | Poland | Landcover.ai | https://landcover.ai.linuxpolska.com/ | Head Office of Geodesy and Cartography | CC BY-NC-SA 4.0 |
| Ngaoundere | Cameroon | Open Cities AI | https://www.drivendata.org/competitions/60/building-segmentation-disaster-resilience/ | Global Facility for Disaster Reduction and Recovery | CC BY 4.0 |
| Kinshasa | Congo | Open Cities AI | https://www.drivendata.org/competitions/60/building-segmentation-disaster-resilience/ | Global Facility for Disaster Reduction and Recovery | CC BY 4.0 |
| Pointenoire | Congo | Open Cities AI | https://www.drivendata.org/competitions/60/building-segmentation-disaster-resilience/ | Global Facility for Disaster Reduction and Recovery | CC BY 4.0 |
| Accra | Ghana | Open Cities AI | https://www.drivendata.org/competitions/60/building-segmentation-disaster-resilience/ | Global Facility for Disaster Reduction and Recovery | CC BY 4.0 |
| Monrovia | Liberia | Open Cities AI | https://www.drivendata.org/competitions/60/building-segmentation-disaster-resilience/ | Global Facility for Disaster Reduction and Recovery | CC BY 4.0 |
| Niamey | Niger | Open Cities AI | https://www.drivendata.org/competitions/60/building-segmentation-disaster-resilience/ | Global Facility for Disaster Reduction and Recovery | CC BY 4.0 |
| Mahe | Seychelles | Open Cities AI | https://www.drivendata.org/competitions/60/building-segmentation-disaster-resilience/ | Global Facility for Disaster Reduction and Recovery | CC BY 4.0 |
| Dar es salaam | Tanzania | Open Cities AI | https://www.drivendata.org/competitions/60/building-segmentation-disaster-resilience/ | Global Facility for Disaster Reduction and Recovery | CC BY 4.0 |
| Dar es salaam | Tanzania | Open Cities AI | https://www.drivendata.org/competitions/60/building-segmentation-disaster-resilience/ | Global Facility for Disaster Reduction and Recovery | CC BY 4.0 |
| Zanzibar | Tanzania | Open Cities AI | https://www.drivendata.org/competitions/60/building-segmentation-disaster-resilience/ | Global Facility for Disaster Reduction and Recovery | CC BY 4.0 |
| Kampala | Uganda | Open Cities AI | https://www.drivendata.org/competitions/60/building-segmentation-disaster-resilience/ | Global Facility for Disaster Reduction and Recovery | CC BY 4.0 |
| Buenos aires | Argentina | Open data | https://map.openaerialmap.org | Municipalidad de Pergamino | CC BY 4.0 |
| Rosario | Argentina | Open data | https://map.openaerialmap.org | Julia Faraudello | CC BY 4.0 |
| Melbourne | Australia | Open data | https://map.openaerialmap.org | City of Melbourne | CC BY 4.0 |
| Cox’s bazar | Bangladesh | Open data | https://map.openaerialmap.org | IOM Bangladesh - Needs and Population Monitoring (NPM) Drone | CC BY 4.0 |
| Cox’s bazar | Bangladesh | Open data | https://map.openaerialmap.org | IOM Bangladesh - Needs and Population Monitoring (NPM) Drone | CC BY 4.0 |
| Dhaka | Bangladesh | Open data | https://map.openaerialmap.org | AIGEO Center | CC BY 4.0 |
| Santiago | Chile | Open data | https://map.openaerialmap.org | SECTRA | CC BY 4.0 |
| Bogota | Colombia | Open data | https://map.openaerialmap.org | Maptime Bogota | CC BY 4.0 |
| Svaneti | Georgia | Open data | https://map.openaerialmap.org | Transcaucasian Trail Association | CC BY 4.0 |
| Accra | Ghana | Open data | https://map.openaerialmap.org | Environmental Protection Agency Ghana | CC BY 4.0 |
| Western | Ghana | Open data | https://map.openaerialmap.org | UMaT YouthMappers | CC BY 4.0 |
| Al qurnah | Iraq | Open data | https://map.openaerialmap.org | Bilal Koç | CC BY 4.0 |
| Kyoto | Japan | Open data | https://maps.gsi.go.jp/development/ichiran.html | Geospatial Information Authority of Japan |  |
| Tokyo | Japan | Open data | https://maps.gsi.go.jp/development/ichiran.html | Geospatial Information Authority of Japan |  |
| Monrovia | Liberia | Open data | https://map.openaerialmap.org | Uhurulabs | CC BY 4.0 |
| Dowa | Malawi | Open data | https://map.openaerialmap.org | MapMalawi | CC BY 4.0 |
| Ulaanbaatar | Mongolia | Open data | https://map.openaerialmap.org | City of Ulaanbaatar and Asia Foundation | CC BY 4.0 |
| Maputo | Mozambique | Open data | https://map.openaerialmap.org | MapeandoMeuBairro | CC BY 4.0 |
| Abancay | Peru | Open data | https://sigrid.cenepred.gob.pe | National Center for Disaster Risk Estimation, Prevention and Reduction |  |
| Chiclayo | Peru | Open data | https://sigrid.cenepred.gob.pe | National Center for Disaster Risk Estimation, Prevention and Reduction |  |
| Chincha | Peru | Open data | https://sigrid.cenepred.gob.pe | National Center for Disaster Risk Estimation, Prevention and Reduction |  |
| Ica | Peru | Open data | https://sigrid.cenepred.gob.pe | National Center for Disaster Risk Estimation, Prevention and Reduction |  |
| Lambayeque | Peru | Open data | https://sigrid.cenepred.gob.pe | National Center for Disaster Risk Estimation, Prevention and Reduction |  |
| Lima | Peru | Open data | https://sigrid.cenepred.gob.pe | National Center for Disaster Risk Estimation, Prevention and Reduction |  |
| Pisco | Peru | Open data | https://sigrid.cenepred.gob.pe | National Center for Disaster Risk Estimation, Prevention and Reduction |  |
| Piura | Peru | Open data | https://sigrid.cenepred.gob.pe | National Center for Disaster Risk Estimation, Prevention and Reduction |  |
| Sechura | Peru | Open data | https://sigrid.cenepred.gob.pe | National Center for Disaster Risk Estimation, Prevention and Reduction |  |
| Viru | Peru | Open data | https://sigrid.cenepred.gob.pe | National Center for Disaster Risk Estimation, Prevention and Reduction |  |
| Baybay | Philippines | Open data | https://map.openaerialmap.org | SkyEye | CC BY 4.0 |
| San tome | Sao Tome and Principe | Open data | https://map.openaerialmap.org | Drones Adventures | CC BY 4.0 |
| Chiangmai | Tailand | Open data | https://map.openaerialmap.org | UR Field Lab Chiang Mai | CC BY 4.0 |
| Lohur | Tajikistan | Open data | https://map.openaerialmap.org | FAZO Institute, Dushanbe, Tajikistan | CC BY 4.0 |
| Kagera | Tanzania | Open data | https://map.openaerialmap.org | WeRobotics | CC BY 4.0 |
| Zanzibar | Tanzania | Open data | https://map.openaerialmap.org | Commission for Lands and Revolutionary Government of Zanzibar | CC BY 4.0 |
| Tonga | Tonga | Open data | https://map.openaerialmap.org | World Bank, V-TOL Aerospace | CC BY 4.0 |
| Soriano | Uruguay | Open data | https://map.openaerialmap.org | IntelDrones SRL | CC BY 4.0 |
| Rio | Brazil | SpaceNet | https://spacenet.ai/spacenet-buildings-dataset-v1/ | Maxar | CC BY-SA 4.0 |
| Shanghai | China | SpaceNet | https://spacenet.ai/spacenet-buildings-dataset-v2/ | Maxar | CC BY-SA 4.0 |
| Paris | France | SpaceNet | https://spacenet.ai/spacenet-buildings-dataset-v2/ | Maxar | CC BY-SA 4.0 |
| Rotterdam | Netherlands | SpaceNet | https://spacenet.ai/sn6-challenge/ | Maxar | CC BY-SA 4.0 |
| Khartoum | Sudan | SpaceNet | https://spacenet.ai/spacenet-buildings-dataset-v2/ | Maxar | CC BY-SA 4.0 |
| Vegas | USA | SpaceNet | https://spacenet.ai/spacenet-buildings-dataset-v2/ | Maxar | CC BY-SA 4.0 |
| Adelaide | Australia | xBD | https://xview2.org/ | Maxar | CC BY-NC-SA 4.0 |
| El rodeo | Guatemala | xBD | https://xview2.org/ | Maxar | CC BY-NC-SA 4.0 |
| Jeremie | Haiti | xBD | https://xview2.org/ | Maxar | CC BY-NC-SA 4.0 |
| Les-cayes | Haiti | xBD | https://xview2.org/ | Maxar | CC BY-NC-SA 4.0 |
| Port-a-piment | Haiti | xBD | https://xview2.org/ | Maxar | CC BY-NC-SA 4.0 |
| Saint-louis-du-sud | Haiti | xBD | https://xview2.org/ | Maxar | CC BY-NC-SA 4.0 |
| Palu | Indonesia | xBD | https://xview2.org/ | Maxar | CC BY-NC-SA 4.0 |
| Labuhan | Malaysia | xBD | https://xview2.org/ | Maxar | CC BY-NC-SA 4.0 |
| Mexico city | Mexico | xBD | https://xview2.org/ | Maxar | CC BY-NC-SA 4.0 |
| Gorakhpur | Nepal | xBD | https://xview2.org/ | Maxar | CC BY-NC-SA 4.0 |
| Pedrogao grande | Portugal | xBD | https://xview2.org/ | Maxar | CC BY-NC-SA 4.0 |
| Houston | USA | xBD | https://xview2.org/ | Maxar | CC BY-NC-SA 4.0 |
| Joplin | USA | xBD | https://xview2.org/ | Maxar | CC BY-NC-SA 4.0 |
| Leilane estates | USA | xBD | https://xview2.org/ | Maxar | CC BY-NC-SA 4.0 |
| Little rock | USA | xBD | https://xview2.org/ | Maxar | CC BY-NC-SA 4.0 |
| Oklahoma | USA | xBD | https://xview2.org/ | Maxar | CC BY-NC-SA 4.0 |
| Panama city | USA | xBD | https://xview2.org/ | Maxar | CC BY-NC-SA 4.0 |
| Santa rosa | USA | xBD | https://xview2.org/ | Maxar | CC BY-NC-SA 4.0 |
| Thousand oaks | USA | xBD | https://xview2.org/ | Maxar | CC BY-NC-SA 4.0 |
| Tulsa | USA | xBD | https://xview2.org/ | Maxar | CC BY-NC-SA 4.0 |
| Tuscaloosa | USA | xBD | https://xview2.org/ | Maxar | CC BY-NC-SA 4.0 |
| Wallace | USA | xBD | https://xview2.org/ | Maxar | CC BY-NC-SA 4.0 |
