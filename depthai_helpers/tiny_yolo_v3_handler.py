from math import exp as exp
import cv2
import numpy as np
from time import time
from depthai_helpers.tensor_utils import get_tensor_output, get_tensor_outputs_list, get_tensor_outputs_dict

# Adjust these thresholds
detection_threshold = 0.60

class YoloParams:
    # ------------------------------------------- Extracting layer parameters ------------------------------------------
    def __init__(self, side):
        self.num = 3 
        self.coords = 4 
        self.classes = 80
        self.anchors = [10,14, 23,27, 37,58, 81,82, 135,169, 344,319]

        if side == 26:
            mask=[1,2,3]
            self.num = len(mask)
        else:
            mask=[3,4,5]
            self.num = len(mask)

        maskedAnchors = []
        for idx in mask:
            maskedAnchors += [self.anchors[idx * 2], self.anchors[idx * 2 + 1]]
        self.anchors = maskedAnchors
        self.side = side
   
    def log_params(self):
        params_to_print = {'classes': self.classes, 'num': self.num, 'coords': self.coords, 'anchors': self.anchors}
        [log.info("         {:8}: {}".format(param_name, param)) for param_name, param in params_to_print.items()]


def entry_index(side, coord, classes, location, entry):
    side_power_2 = side ** 2
    n = location // side_power_2
    loc = location % side_power_2
    return int(side_power_2 * (n * (coord + classes + 1) + entry) + loc)



def scale_bbox(x, y, h, w, class_id, confidence, h_scale, w_scale):
    xmin = int((x - w / 2) * w_scale)
    ymin = int((y - h / 2) * h_scale)
    xmax = int(xmin + w * w_scale)
    ymax = int(ymin + h * h_scale)
    return dict(xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax, class_id=class_id, confidence=confidence)


def parse_yolo_region(blob, resized_image_shape, original_im_shape, params, threshold):
    # ------------------------------------------ Validating output parameters ------------------------------------------
    _, _, out_blob_h, out_blob_w = blob.shape
    assert out_blob_w == out_blob_h, "Invalid size of output blob. It sould be in NCHW layout and height should " \
                                     "be equal to width. Current height = {}, current width = {}" \
                                     "".format(out_blob_h, out_blob_w)

    # ------------------------------------------ Extracting layer parameters -------------------------------------------
    orig_im_h, orig_im_w = original_im_shape
    resized_image_h, resized_image_w = resized_image_shape
    objects = list()
    predictions = blob.flatten()
    #replace side , params.side with out_blob_h
    side_square = out_blob_h **2



    # ------------------------------------------- Parsing YOLO Region output -------------------------------------------
    for i in range(side_square):
        row = i // out_blob_h
        col = i % out_blob_h
        for n in range(params.num):
            obj_index = entry_index(out_blob_h, params.coords, params.classes, n * side_square + i, params.coords)
            scale = predictions[obj_index]
            
            if scale < threshold:
                continue
            box_index = entry_index(out_blob_h, params.coords, params.classes, n * side_square + i, 0)
            # Network produces location predictions in absolute coordinates of feature maps.
            # Scale it to relative coordinates.
            x = (col + predictions[box_index + 0 * side_square]) / out_blob_h
            y = (row + predictions[box_index + 1 * side_square]) / out_blob_h

            
            # Value for exp is very big number in some cases so following construction is using here
            try:
                w_exp = exp(predictions[box_index + 2 * side_square])
                h_exp = exp(predictions[box_index + 3 * side_square])
            except OverflowError:
                continue
            # Depends on topology we need to normalize sizes by feature maps (up to YOLOv3) or by input shape (YOLOv3)
            w = w_exp * params.anchors[2 * n] / (resized_image_w) #if params.isYoloV3 else params.side)
            h = h_exp * params.anchors[2 * n + 1] / (resized_image_h)# if params.isYoloV3 else params.side)
            for j in range(params.classes):
                class_index = entry_index(out_blob_h, params.coords, params.classes, n * side_square + i,
                                          params.coords + 1 + j)
                confidence = scale * predictions[class_index]
                if confidence < threshold:
                    continue
                objects.append(scale_bbox(x=x, y=y, h=h, w=w, class_id=j, confidence=confidence,
                                          h_scale=orig_im_h, w_scale=orig_im_w))
    return objects


def intersection_over_union(box_1, box_2):
    width_of_overlap_area = min(box_1['xmax'], box_2['xmax']) - max(box_1['xmin'], box_2['xmin'])
    height_of_overlap_area = min(box_1['ymax'], box_2['ymax']) - max(box_1['ymin'], box_2['ymin'])
    if width_of_overlap_area < 0 or height_of_overlap_area < 0:
        area_of_overlap = 0
    else:
        area_of_overlap = width_of_overlap_area * height_of_overlap_area
    box_1_area = (box_1['ymax'] - box_1['ymin']) * (box_1['xmax'] - box_1['xmin'])
    box_2_area = (box_2['ymax'] - box_2['ymin']) * (box_2['xmax'] - box_2['xmin'])
    area_of_union = box_1_area + box_2_area - area_of_overlap
    if area_of_union == 0:
        return 0
    return area_of_overlap / area_of_union


def decode_tiny_yolo(nnet_packet, **kwargs):
    NN_metadata = kwargs['NN_json']
    output_format = NN_metadata['NN_config']['output_format']

    if output_format == "detection":
        objects = list()
        detection_nr = nnet_packet.getDetectionCount()
        for i in range(detection_nr):
            detection = nnet_packet.getDetectedObject(i)
            score = detection.get_score()
            detection = nnet_packet.getDetectedObject(i)
            class_id = detection.get_label_id()
            xmin = int(detection.get_xmin() * 416)
            xmax = int(detection.get_xmax() * 416)
            ymin = int(detection.get_ymin() * 416)
            ymax = int(detection.get_ymax() * 416)
            distance_x = detection.get_depth_x()
            distance_y = detection.get_depth_y()
            distance_z = detection.get_depth_z()
            scaled_object = dict(xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax, class_id=class_id, confidence=score, depth_x=distance_x, depth_y=distance_y, depth_z=distance_z)
            objects.append(scaled_object)

        return objects
    else:
        
        output_list = get_tensor_outputs_list(nnet_packet)

        
        #render_time = 0
        #parsing_time = 0

        # ----------------------------------------------- 6. Doing inference -----------------------------------------------
        #log.info("Starting inference...")

        objects = list()
        resized_image_shape =[416,416]
        original_image_shape =[416,416]
        iou_threshold = NN_metadata['NN_config']['NN_specific_metadata']['iou_threshold']


        start_time = time()
        for out_blob in output_list:

            l_params = YoloParams(out_blob.shape[2])
            objects += parse_yolo_region(out_blob,  resized_image_shape,
                                                original_image_shape, l_params,
                                                detection_threshold)
            parsing_time = time() - start_time

        # Filtering overlapping boxes with respect to the --iou_threshold CLI parameter
        objects = sorted(objects, key=lambda obj : obj['confidence'], reverse=True)
        for i in range(len(objects)):
            if objects[i]['confidence'] == 0:
                continue
            for j in range(i + 1, len(objects)):
                if intersection_over_union(objects[i], objects[j]) > iou_threshold:
                        objects[j]['confidence'] = 0
    
        return objects

BOX_COLOR = (0,255,0)
LABEL_BG_COLOR = (70, 120, 70) # greyish green background for text
TEXT_COLOR = (255, 255, 255)   # white text
TEXT_FONT = cv2.FONT_HERSHEY_SIMPLEX

def show_tiny_yolo(filtered_objects, frame, **kwargs):
    NN_metadata = kwargs['NN_json']
    labels = NN_metadata['mappings']['labels']
    config = kwargs['config']

    filtered_objects = [obj for obj in filtered_objects if obj['confidence'] >= detection_threshold]
    for object_index in range(len(filtered_objects)):
        
        # get all values from the filtered object list
        xmin = filtered_objects[object_index]['xmin']
        ymin = filtered_objects[object_index]['ymin']
        xmax = filtered_objects[object_index]['xmax']
        ymax = filtered_objects[object_index]['ymax']
        confidence = filtered_objects[object_index]['confidence']
        class_id = filtered_objects[object_index]['class_id']
       
            # Set up the text for display
        cv2.rectangle(frame,(xmin, ymin), (xmax, ymin+20), LABEL_BG_COLOR, -1)
        cv2.putText(frame, labels[class_id] + ': %.2f' % confidence, (xmin+5, ymin+15), TEXT_FONT, 0.5, TEXT_COLOR, 1)
            # Set up the bounding box
        cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), BOX_COLOR, 1)
        if config['ai']['calc_dist_to_bb']:
            distance_x = filtered_objects[object_index]['depth_x']
            distance_y = filtered_objects[object_index]['depth_y']
            distance_z = filtered_objects[object_index]['depth_z']
            cv2.putText(frame, 'x:' '{:7.3f}'.format(distance_x) + ' m', (xmin, ymin+60),  TEXT_FONT, 0.5, TEXT_COLOR)
            cv2.putText(frame, 'y:' '{:7.3f}'.format(distance_y) + ' m', (xmin, ymin+80),  TEXT_FONT, 0.5, TEXT_COLOR)
            cv2.putText(frame, 'z:' '{:7.3f}'.format(distance_z) + ' m', (xmin, ymin+100), TEXT_FONT, 0.5, TEXT_COLOR)
    return frame
