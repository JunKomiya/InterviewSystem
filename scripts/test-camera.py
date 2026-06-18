import os
import sys

# Windows protobuf parsing fix for MediaPipe (reread / relaunch if not set at OS level)
if os.environ.get('PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION') != 'python':
    os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'
    script_path = os.path.abspath(__file__)
    args = [sys.executable, script_path] + sys.argv[1:]
    
    quoted_args = []
    for arg in args:
        if ' ' in arg and not (arg.startswith('"') and arg.endswith('"')):
            quoted_args.append(f'"{arg}"')
        else:
            quoted_args.append(arg)
            
    os.execv(sys.executable, quoted_args)

import cv2
import mediapipe as mp

# MediaPipeの必要なモジュールをシンプルに定義
mp_face_mesh = mp.solutions.face_mesh
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

# カメラのキャプチャを開始 (0は内蔵カメラ)
cap = cv2.VideoCapture(0)

# Face Meshモデルの読み込み
with mp_face_mesh.FaceMesh(
    max_num_faces=1,             # 認識する顔は最大1つ
    refine_landmarks=True,       # Trueにすることで「黒目（虹彩）」の座標も取得可能に
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
) as face_mesh:

    print("==================================================")
    print("カメラを起動しました。")
    print("ウインドウを選択した状態で、キーボードの『q』を押すと終了します。")
    print("==================================================")

    while cap.isOpened():
        success, image = cap.read()
        if not success:
            print("カメラからの映像を取得できませんでした。")
            break

        # OpenCVはBGR形式なので、MediaPipe用にRGBに変換
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(image_rgb)

        # 画面に顔のメッシュを描画
        if results.multi_face_landmarks:
            for face_landmarks in results.multi_face_landmarks:
                
                # 1. 顔全体の細かい網の目（メッシュ）を描画
                mp_drawing.draw_landmarks(
                    image=image,
                    landmark_list=face_landmarks,
                    connections=mp_face_mesh.FACEMESH_TESSELATION,
                    landmark_drawing_spec=None,
                    connection_drawing_spec=mp_drawing_styles.get_default_face_mesh_tesselation_style()
                )
                
                # 2. 「黒目（虹彩）」の輪郭を青い線で描画
                mp_drawing.draw_landmarks(
                    image=image,
                    landmark_list=face_landmarks,
                    connections=mp_face_mesh.FACEMESH_IRISES,
                    landmark_drawing_spec=None,
                    connection_drawing_spec=mp_drawing_styles.get_default_face_mesh_iris_connections_style()
                )

        # 映像を表示（鏡になるように左右反転）
        cv2.imshow('MediaPipe Face Mesh (Test)', cv2.flip(image, 1))

        # 'q' キーが押されたらループを抜ける
        if cv2.waitKey(5) & 0xFF == ord('q'):
            break

cap.release()
cv2.destroyAllWindows()