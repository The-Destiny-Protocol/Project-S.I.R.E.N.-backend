import os
import cv2
from ultralytics import YOLO

class EdgeVisionNode:
    def __init__(self, model_path="yolov8s.pt"):
        weight_path = "edge_node/vision/weights/best.pt"
        self.model = YOLO(weight_path)
        # if os.path.exists(weight_path):
        #     self.model = YOLO(weight_path)
        # else:
        #     print(f"Warning: Custom weights {weight_path} not found. Falling back to default yolov8n.pt")
        #     self.model = YOLO("yolov8n.pt")
        self.camera = cv2.VideoCapture(0)
    def process_stream(self):
        while self.camera.isOpened():
            success, frame = self.camera.read()
            if not success:
                break
            results = self.model.track(frame, persist=True)
            for result in results:
                boxes = result.boxes

            annotated_frame = results[0].plot()
            cv2.imshow("Edge Node - Obstruction Scanner", annotated_frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
        self.camera.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    node = EdgeVisionNode()
    node.process_stream()