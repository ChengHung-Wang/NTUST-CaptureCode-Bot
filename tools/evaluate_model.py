import os
import re
import glob
import argparse
import json
import ddddocr


def find_first(pattern):
    items = glob.glob(pattern)
    return items[0] if items else None


def normalize(s):
    return re.sub(r'\s+', '', s or '').strip()


def main():
    parser = argparse.ArgumentParser(description='Evaluate ONNX model on labeled images (filename: label_xxx.png)')
    parser.add_argument('--model', '-m', help='Path to ONNX model (default: detect in tools/)', default=None)
    parser.add_argument('--charset', '-c', help='Path to charsets.json (default: detect in tools/)', default=None)
    parser.add_argument('--images', '-i', help='Folder with labeled images (default: tools/correct)', default='./tools/correct')
    args = parser.parse_args()

    # Auto-detect model and charset if not provided
    model_path = args.model
    if not model_path:
        model_path = find_first(os.path.join('tools', '*.onnx'))
    if not model_path or not os.path.exists(model_path):
        raise FileNotFoundError('ONNX model not found in tools/. Provide --model')

    charset_path = args.charset
    if not charset_path:
        # try common names first
        candidates = [os.path.join('tools', 'charsets.json'), find_first(os.path.join('tools', '*charset*.json'))]
        charset_path = next((p for p in candidates if p and os.path.exists(p)), None)
    if not charset_path or not os.path.exists(charset_path):
        raise FileNotFoundError('charsets.json not found in tools/. Provide --charset')

    images_dir = args.images
    if not os.path.exists(images_dir):
        raise FileNotFoundError(f'Images folder not found: {images_dir}')

    print(f'Loading model: {model_path}')
    print(f'Loading charsets: {charset_path}')

    ocr = ddddocr.DdddOcr(det=False, ocr=True, import_onnx_path=model_path, charsets_path=charset_path, show_ad=False)

    exts = {'.png', '.jpg', '.jpeg', '.gif', '.bmp'}
    files = [p for p in glob.glob(os.path.join(images_dir, '*')) if os.path.splitext(p)[1].lower() in exts]
    if not files:
        print('No image files found in', images_dir)
        return

    total = 0
    correct = 0
    wrong_cases = []

    for p in sorted(files):
        fname = os.path.basename(p)
        m = re.match(r'^([^_]+)_', fname)
        if not m:
            # skip files not matching label_*.png
            continue
        true_label = m.group(1)
        with open(p, 'rb') as f:
            img_bytes = f.read()
        pred = ocr.classification(img_bytes)

        total += 1
        if normalize(pred) == normalize(true_label):
            correct += 1
        else:
            wrong_cases.append((p, true_label, pred))

    acc = correct / total if total else 0.0
    print(f'Total: {total}, Correct: {correct}, Accuracy: {acc:.4f}')

    if wrong_cases:
        print('\nWrong samples (up to 50):')
        for p, t, pr in wrong_cases[:50]:
            print(f'- {p}  true="{t}"  pred="{pr}"')


if __name__ == '__main__':
    main()
