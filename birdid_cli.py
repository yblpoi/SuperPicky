#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BirdID CLI - 独立鸟类识别命令行工具
支持完整的 eBird 区域过滤参数

Usage:
    python birdid_cli.py bird.jpg
    python birdid_cli.py bird.NEF --country AU --region AU-SA
    python birdid_cli.py bird.jpg --no-ebird
    python birdid_cli.py ~/Photos/*.jpg --batch --write-exif
"""

import argparse
import sys
import os
from pathlib import Path

# 确保模块路径正确
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tools.i18n import t


def print_banner():
    """打印 CLI 横幅"""
    print("\n" + "=" * 60)
    print(t("cli.birdid_banner"))
    print("=" * 60)


def identify_single(args, image_path: str) -> dict:
    """识别单张图片"""
    model_type = getattr(args, 'model', 'birdid2024')

    if model_type == 'osea':
        return identify_single_osea(args, image_path)
    else:
        return identify_single_birdid2024(args, image_path)


def identify_single_birdid2024(args, image_path: str) -> dict:
    """使用 birdid2024 模型识别"""
    from birdid.bird_identifier import identify_bird

    result = identify_bird(
        image_path,
        use_yolo=args.yolo,
        use_gps=args.gps,
        use_ebird=args.ebird,
        country_code=args.country,
        region_code=args.region,
        top_k=args.top
    )

    return result


def identify_single_osea(args, image_path: str) -> dict:
    """使用 OSEA 模型识别"""
    from birdid.osea_classifier import get_osea_classifier
    from birdid.bird_identifier import load_image, get_yolo_detector, YOLO_AVAILABLE

    result = {
        'success': False,
        'image_path': image_path,
        'results': [],
        'yolo_info': None,
        'model': 'osea',
        'error': None
    }

    try:
        # 加载图像
        image = load_image(image_path)

        # YOLO 裁剪 (可选)
        if args.yolo and YOLO_AVAILABLE:
            width, height = image.size
            if max(width, height) > 640:
                detector = get_yolo_detector()
                if detector:
                    cropped, info = detector.detect_and_crop_bird(image)
                    if cropped:
                        image = cropped
                        result['yolo_info'] = info
                    else:
                        # 严格模式：YOLO 未检测到鸟类，直接短路返回
                        result['success'] = True
                        result['results'] = []
                        result['yolo_info'] = {'bird_count': 0}
                        return result

        # 获取 OSEA 分类器
        classifier = get_osea_classifier()

        # 预测
        use_tta = getattr(args, 'tta', False)
        if use_tta:
            predictions = classifier.predict_with_tta(image, top_k=args.top)
        else:
            predictions = classifier.predict(image, top_k=args.top)

        result['success'] = True
        result['results'] = predictions

    except Exception as e:
        result['error'] = str(e)

    return result


def display_result(result: dict, verbose: bool = True):
    """显示识别结果"""
    if not result['success']:
        print(t("cli.identify_fail", error=result.get('error', 'Unknown')))
        return False
    
    if verbose:
        print(f"\n{'─' * 50}")

        # 显示使用的模型
        model_name = result.get('model', 'birdid2024')
        if model_name == 'osea':
            print("🤖 模型: OSEA (10,964 物种)")

        if result.get('yolo_info'):
            print(t("cli.yolo_info", info=result['yolo_info']))

        if result.get('gps_info'):
            gps = result['gps_info']
            print(t("cli.gps_info", info=gps['info']))

        if result.get('ebird_info'):
            ebird = result['ebird_info']
            if ebird.get('enabled'):
                print(t("cli.ebird_info", region=ebird.get('region_code', 'N/A'), count=ebird.get('species_count', 0)))
            # 回退提示（优先国家级，其次全局）
            if ebird.get('country_fallback'):
                print(f"⚠️  {t('server.country_fallback_warning', country=ebird.get('country_code', '?'))}")
            elif ebird.get('gps_fallback'):
                print(f"⚠️  {t('server.gps_fallback_warning', count=ebird.get('species_count', 0))}")
    
    results = result.get('results', [])
    if not results:
        print(t("cli.no_bird"))
        print(t("cli.no_bird_hint"))
        return False
    
    print(t("cli.result_title", count=len(results)))
    for i, r in enumerate(results, 1):
        cn_name = r.get('cn_name', '未知')
        en_name = r.get('en_name', 'Unknown')
        confidence = r.get('confidence', 0)
        ebird_match = "✓eBird" if r.get('ebird_match') else ""
        scientific_name = r.get('scientific_name', '')

        print(f"  {i}. {cn_name} ({en_name})")
        if scientific_name:
            print(f"     学名: {scientific_name}")
        print(f"     置信度: {confidence:.1f}% {ebird_match}")

    return True


def write_exif(image_path: str, result: dict, threshold: float = 70.0) -> bool:
    """将识别结果写入 EXIF"""
    from tools.exiftool_manager import get_exiftool_manager
    
    results = result.get('results', [])
    if not results:
        return False
    
    best = results[0]
    confidence = best.get('confidence', 0)
    
    if confidence < threshold:
        print(t("cli.confidence_skip", confidence=confidence, threshold=threshold))
        return False
    
    bird_name = f"{best['cn_name']} ({best['en_name']})"
    
    exiftool_mgr = get_exiftool_manager()
    
    stats = exiftool_mgr.batch_set_metadata([{
        'file': image_path,
        'title': bird_name,
        'caption': bird_name,
    }])

    return stats.get('success', 0) > 0


def cmd_identify(args):
    """识别命令"""
    print_banner()
    
    images = args.images
    
    # 展开 glob 模式
    expanded_images = []
    for img in images:
        if '*' in img or '?' in img:
            from glob import glob
            expanded_images.extend(glob(img))
        else:
            expanded_images.append(img)
    
    images = [img for img in expanded_images if os.path.isfile(img)]
    
    if not images:
        print(t("cli.no_files"))
        return 1
    
    # 显示设置
    model_type = getattr(args, 'model', 'birdid2024')
    use_tta = getattr(args, 'tta', False)

    print(f"\n📸 图片数量: {len(images)}")
    print(f"🤖 模型: {model_type.upper()}" + (" + TTA" if model_type == 'osea' and use_tta else ""))
    print(f"⚙️  YOLO裁剪: {'是' if args.yolo else '否'}")
    if model_type == 'birdid2024':
        print(f"⚙️  GPS自动检测: {'是' if args.gps else '否'}")
        print(f"⚙️  eBird过滤: {'是' if args.ebird else '否'}")
        if args.country:
            print(f"  └─ 国家: {args.country}")
        if args.region:
            print(f"  └─ 区域: {args.region}")
    print(f"⚙️  返回数量: {args.top}")
    if args.write_exif:
        print(f"⚙️  写入EXIF: 是 (阈值: {args.threshold}%)")
    print()
    
    # 批量模式
    if len(images) > 1 or args.batch:
        return batch_identify(args, images)
    
    # 单张识别
    image_path = os.path.abspath(images[0])
    print(f"📸 图片: {os.path.basename(image_path)}")
    
    print("🔍 正在识别...")
    result = identify_single(args, image_path)
    
    success = display_result(result, verbose=True)
    
    # 写入 EXIF
    if args.write_exif and success:
        print(f"\n📝 写入 EXIF...")
        if write_exif(image_path, result, args.threshold):
            print(f"  ✅ 已写入: {result['results'][0]['cn_name']}")
        else:
            print(f"  ❌ 写入失败")
    
    print()
    return 0 if success else 1


def batch_identify(args, images: list):
    """批量识别"""
    print(f"{'═' * 60}")
    print(f"  批量识别模式 - 共 {len(images)} 张图片")
    print(f"{'═' * 60}\n")
    
    stats = {
        'total': len(images),
        'success': 0,
        'failed': 0,
        'written': 0,
        'species': {}
    }
    
    for i, image_path in enumerate(images, 1):
        image_path = os.path.abspath(image_path)
        filename = os.path.basename(image_path)
        
        print(f"[{i}/{stats['total']}] {filename}")
        
        try:
            result = identify_single(args, image_path)
            
            if result['success'] and result.get('results'):
                stats['success'] += 1
                
                # 显示 Top 1 结果
                best = result['results'][0]
                cn_name = best.get('cn_name', '未知')
                confidence = best.get('confidence', 0)
                print(f"  → {cn_name} ({confidence:.1f}%)")
                
                # 统计物种
                if cn_name not in stats['species']:
                    stats['species'][cn_name] = 0
                stats['species'][cn_name] += 1
                
                # 写入 EXIF
                if args.write_exif:
                    if write_exif(image_path, result, args.threshold):
                        stats['written'] += 1
                        print(f"    ✅ 已写入EXIF")
            else:
                stats['failed'] += 1
                error = result.get('error', '无法识别')
                print(f"  ⚠️  {error}")
                
        except Exception as e:
            stats['failed'] += 1
            print(f"  ❌ 错误: {e}")
    
    # 打印统计
    print(f"\n{'═' * 60}")
    print(f"  批量识别完成")
    print(f"{'═' * 60}")
    print(f"\n📊 统计:")
    print(f"  成功: {stats['success']}/{stats['total']}")
    print(f"  失败: {stats['failed']}/{stats['total']}")
    if args.write_exif:
        print(f"  写入EXIF: {stats['written']}")
    
    if stats['species']:
        print(f"\n🐦 识别到的物种 ({len(stats['species'])} 种):")
        sorted_species = sorted(stats['species'].items(), key=lambda x: -x[1])
        for species, count in sorted_species[:10]:
            print(f"  • {species}: {count} 张")
        if len(sorted_species) > 10:
            print(f"  ... 以及 {len(sorted_species) - 10} 种其他物种")
    
    print()
    return 0 if stats['failed'] < stats['total'] else 1


def cmd_organize(args):
    """批量识别并按鸟种分目录"""
    import shutil
    import json
    from birdid.bird_identifier import identify_bird
    from tools.exiftool_manager import get_exiftool_manager
    
    print_banner()
    
    directory = os.path.abspath(args.directory)
    if not os.path.isdir(directory):
        print(f"❌ 目录不存在: {directory}")
        return 1
    
    print(f"\n📂 目录: {directory}")
    print(f"⚙️  置信度阈值: {args.threshold}%")
    print(f"⚙️  eBird过滤: {'是' if args.ebird else '否'}")
    if args.country:
        print(f"  └─ 国家: {args.country}")
    if args.region:
        print(f"  └─ 区域: {args.region}")
    print(f"⚙️  写入EXIF: {'是' if args.write_exif else '否'}")
    
    # 扫描图片文件
    extensions = {'.jpg', '.jpeg', '.png', '.nef', '.arw', '.cr2', '.cr3', '.rw2', '.orf', '.dng', '.raf'}
    images = []
    for filename in os.listdir(directory):
        if filename.startswith('.'):
            continue
        ext = os.path.splitext(filename)[1].lower()
        if ext in extensions:
            images.append(os.path.join(directory, filename))
    
    if not images:
        print("\n❌ 未找到图片文件")
        return 1
    
    print(f"\n📸 找到 {len(images)} 个图片文件")
    
    if not args.yes:
        confirm = input("\n⚠️  将按鸟种分目录，确定继续? [y/N]: ")
        if confirm.lower() not in ['y', 'yes']:
            print("❌ 已取消")
            return 1
    
    print(f"\n{'═' * 60}")
    print(f"  开始批量识别并分类")
    print(f"{'═' * 60}\n")
    
    # 用于记录移动操作的 manifest
    manifest_path = os.path.join(directory, '.birdid_manifest.json')
    manifest = {
        'created': str(os.path.getmtime(directory)),
        'moves': []  # [{original: ..., moved_to: ..., species: ...}]
    }
    
    stats = {
        'total': len(images),
        'identified': 0,
        'moved': 0,
        'skipped': 0,
        'failed': 0,
        'species': {}
    }
    
    exiftool_mgr = get_exiftool_manager() if args.write_exif else None
    
    for i, image_path in enumerate(images, 1):
        filename = os.path.basename(image_path)
        print(f"[{i}/{stats['total']}] {filename}")
        
        try:
            result = identify_bird(
                image_path,
                use_yolo=True,
                use_gps=True,
                use_ebird=args.ebird,
                country_code=args.country,
                region_code=args.region,
                top_k=1
            )
            
            if result['success'] and result.get('results'):
                best = result['results'][0]
                cn_name = best.get('cn_name', '未知')
                en_name = best.get('en_name', 'Unknown')
                confidence = best.get('confidence', 0)
                
                print(f"  → {cn_name} ({confidence:.1f}%)")
                
                # 检查置信度
                if confidence < args.threshold:
                    print(f"    ⚠️  置信度不足，跳过分类")
                    stats['skipped'] += 1
                    continue
                
                stats['identified'] += 1
                
                # 创建鸟种目录名 (中文名_英文名)
                safe_cn = cn_name.replace('/', '-').replace('\\', '-')
                safe_en = en_name.replace('/', '-').replace('\\', '-')
                species_folder = f"{safe_cn}_{safe_en}"
                species_dir = os.path.join(directory, species_folder)
                
                # 创建目录
                if not os.path.exists(species_dir):
                    os.makedirs(species_dir)
                
                # 移动文件
                new_path = os.path.join(species_dir, filename)
                if not os.path.exists(new_path):
                    shutil.move(image_path, new_path)
                    stats['moved'] += 1
                    print(f"    📂 移动到: {species_folder}/")
                    
                    # 记录到 manifest
                    manifest['moves'].append({
                        'original': image_path,
                        'moved_to': new_path,
                        'species_cn': cn_name,
                        'species_en': en_name,
                        'confidence': confidence
                    })
                    
                    # 统计物种
                    if cn_name not in stats['species']:
                        stats['species'][cn_name] = 0
                    stats['species'][cn_name] += 1
                    
                    # 写入 EXIF
                    if args.write_exif and exiftool_mgr:
                        bird_name = f"{cn_name} ({en_name})"
                        metadata = {
                            'Title': bird_name,
                            'Caption-Abstract': bird_name,
                        }
                        exiftool_mgr.set_metadata(new_path, metadata)
                else:
                    print(f"    ⚠️  目标文件已存在，跳过")
                    stats['skipped'] += 1
            else:
                stats['failed'] += 1
                print(f"  ⚠️  无法识别")
                
        except Exception as e:
            stats['failed'] += 1
            print(f"  ❌ 错误: {e}")
    
    # 保存 manifest
    if manifest['moves']:
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print(f"\n💾 已保存移动记录: .birdid_manifest.json")
    
    # 打印统计
    print(f"\n{'═' * 60}")
    print(f"  分类完成")
    print(f"{'═' * 60}")
    print(f"\n📊 统计:")
    print(f"  总文件: {stats['total']}")
    print(f"  已识别: {stats['identified']}")
    print(f"  已移动: {stats['moved']}")
    print(f"  跳过: {stats['skipped']}")
    print(f"  失败: {stats['failed']}")
    
    if stats['species']:
        print(f"\n🐦 分类到 {len(stats['species'])} 个鸟种目录:")
        sorted_species = sorted(stats['species'].items(), key=lambda x: -x[1])
        for species, count in sorted_species[:15]:
            print(f"  • {species}/: {count} 张")
        if len(sorted_species) > 15:
            print(f"  ... 以及 {len(sorted_species) - 15} 个其他鸟种目录")
    
    print(f"\n💡 提示: 使用 'birdid_cli.py reset {directory}' 可恢复原始目录结构")
    print()
    return 0


def cmd_reset(args):
    """重置目录 - 恢复原始结构"""
    import shutil
    import json
    
    print_banner()
    
    directory = os.path.abspath(args.directory)
    manifest_path = os.path.join(directory, '.birdid_manifest.json')
    
    print(f"\n🔄 重置目录: {directory}")
    
    # 检查 manifest
    if not os.path.exists(manifest_path):
        print("\n❌ 未找到移动记录 (.birdid_manifest.json)")
        print("   只能重置由 'birdid_cli.py organize' 命令创建的目录结构")
        return 1
    
    # 加载 manifest
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    except Exception as e:
        print(f"\n❌ 无法读取移动记录: {e}")
        return 1
    
    moves = manifest.get('moves', [])
    if not moves:
        print("\n⚠️  移动记录为空，无需重置")
        return 0
    
    print(f"\n📋 找到 {len(moves)} 条移动记录")
    
    if not args.yes:
        confirm = input("\n⚠️  将恢复所有文件到原始位置，确定继续? [y/N]: ")
        if confirm.lower() not in ['y', 'yes']:
            print("❌ 已取消")
            return 1
    
    stats = {'restored': 0, 'skipped': 0, 'failed': 0}
    empty_dirs = set()
    
    for move in moves:
        original = move.get('original')
        moved_to = move.get('moved_to')
        
        if not original or not moved_to:
            continue
        
        if os.path.exists(moved_to):
            try:
                # 确保原始目录存在
                original_dir = os.path.dirname(original)
                if not os.path.exists(original_dir):
                    os.makedirs(original_dir)
                
                # 移动回原位置
                if not os.path.exists(original):
                    shutil.move(moved_to, original)
                    stats['restored'] += 1
                    print(f"  ✅ 恢复: {os.path.basename(original)}")
                    
                    # 记录可能为空的目录
                    empty_dirs.add(os.path.dirname(moved_to))
                else:
                    stats['skipped'] += 1
                    print(f"  ⚠️  跳过 (原位置已有文件): {os.path.basename(original)}")
            except Exception as e:
                stats['failed'] += 1
                print(f"  ❌ 失败: {os.path.basename(original)} - {e}")
        else:
            stats['skipped'] += 1
    
    # 清理空目录
    removed_dirs = 0
    for dir_path in empty_dirs:
        if os.path.exists(dir_path) and os.path.isdir(dir_path):
            try:
                contents = os.listdir(dir_path)
                if len(contents) == 0:
                    os.rmdir(dir_path)
                    removed_dirs += 1
            except:
                pass
    
    # 删除 manifest
    if stats['restored'] > 0:
        try:
            os.remove(manifest_path)
            print(f"\n🗑️  已删除移动记录")
        except:
            pass
    
    # 打印统计
    print(f"\n{'═' * 60}")
    print(f"  重置完成")
    print(f"{'═' * 60}")
    print(f"\n📊 统计:")
    print(f"  已恢复: {stats['restored']}")
    print(f"  跳过: {stats['skipped']}")
    print(f"  失败: {stats['failed']}")
    if removed_dirs > 0:
        print(f"  清理空目录: {removed_dirs}")
    
    print()
    return 0


def cmd_list_countries(args):
    """列出支持的国家代码"""
    print_banner()
    print("\n🗺️  支持的国家代码 (部分):\n")
    
    countries = [
        ("AU", "澳大利亚", "Australia"),
        ("CN", "中国", "China"),
        ("US", "美国", "United States"),
        ("GB", "英国", "United Kingdom"),
        ("JP", "日本", "Japan"),
        ("DE", "德国", "Germany"),
        ("FR", "法国", "France"),
        ("CA", "加拿大", "Canada"),
        ("NZ", "新西兰", "New Zealand"),
        ("IN", "印度", "India"),
        ("BR", "巴西", "Brazil"),
        ("ZA", "南非", "South Africa"),
        ("KR", "韩国", "South Korea"),
        ("TW", "台湾", "Taiwan"),
        ("HK", "香港", "Hong Kong"),
        ("SG", "新加坡", "Singapore"),
        ("MY", "马来西亚", "Malaysia"),
        ("TH", "泰国", "Thailand"),
        ("ID", "印度尼西亚", "Indonesia"),
        ("PH", "菲律宾", "Philippines"),
    ]
    
    for code, cn, en in countries:
        print(f"  {code:4} {cn} ({en})")
    
    print(f"\n💡 提示: 完整列表请参考 eBird 网站: https://ebird.org/explore")
    print()
    return 0


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        prog='birdid_cli',
        description=t("cli.bid_description"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s bird.jpg                        # 识别单张图片 (birdid2024)
  %(prog)s bird.jpg --model osea           # 使用 OSEA 模型识别
  %(prog)s bird.jpg --model osea --tta     # OSEA + TTA (更准但更慢)
  %(prog)s bird.NEF --country AU           # 指定澳大利亚过滤 (birdid2024)
  %(prog)s bird.jpg --region AU-SA         # 指定南澳州过滤
  %(prog)s *.jpg --batch --write-exif      # 批量识别并写入EXIF
  %(prog)s organize ~/Photos/Birds -y      # 按鸟种自动分目录
  %(prog)s reset ~/Photos/Birds -y         # 恢复原始目录结构
  %(prog)s list-countries                  # 列出国家代码
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # ===== 识别命令 (默认) =====
    p_identify = subparsers.add_parser('identify', help='识别鸟类 (默认)')
    p_identify.add_argument('images', nargs='+', help='图片文件路径 (支持 glob 模式)')
    p_identify.add_argument('-t', '--top', type=int, default=5,
                           help='返回前 N 个结果 (默认: 5)')

    # 模型选项
    p_identify.add_argument('--model', '-m', type=str, default='birdid2024',
                           choices=['birdid2024', 'osea'],
                           help='选择模型: birdid2024 (默认) 或 osea')
    p_identify.add_argument('--tta', action='store_true',
                           help='启用 TTA 模式 (仅 OSEA 模型，更准但更慢)')

    # YOLO 选项
    p_identify.add_argument('--no-yolo', action='store_false', dest='yolo',
                           help='禁用 YOLO 裁剪')
    
    # GPS 选项
    p_identify.add_argument('--no-gps', action='store_false', dest='gps',
                           help='禁用 GPS 自动检测')
    
    # eBird 选项
    p_identify.add_argument('--no-ebird', action='store_false', dest='ebird',
                           help='禁用 eBird 区域过滤')
    p_identify.add_argument('--country', '-c', type=str, default=None,
                           help='手动指定国家代码 (如 AU, CN, US)')
    p_identify.add_argument('--region', '-r', type=str, default=None,
                           help='手动指定区域代码 (如 AU-SA, CN-31)')
    
    # 写入选项
    p_identify.add_argument('--write-exif', '-w', action='store_true',
                           help='将识别结果写入 EXIF (Title, Caption, Keywords)')
    p_identify.add_argument('--threshold', type=float, default=70.0,
                           help='写入EXIF的置信度阈值 (默认: 70%%)')
    
    # 批量选项
    p_identify.add_argument('--batch', '-b', action='store_true',
                           help='批量模式 (简化输出)')
    
    p_identify.set_defaults(yolo=True, gps=True, ebird=True)
    
    # ===== 按鸟种分目录命令 =====
    p_organize = subparsers.add_parser('organize', help='批量识别并按鸟种分目录')
    p_organize.add_argument('directory', help='照片目录路径')
    p_organize.add_argument('--threshold', type=float, default=70.0,
                           help='置信度阈值 (默认: 70%%)')
    p_organize.add_argument('--no-ebird', action='store_false', dest='ebird',
                           help='禁用 eBird 区域过滤')
    p_organize.add_argument('--country', '-c', type=str, default=None,
                           help='手动指定国家代码 (如 AU, CN, US)')
    p_organize.add_argument('--region', '-r', type=str, default=None,
                           help='手动指定区域代码 (如 AU-SA, CN-31)')
    p_organize.add_argument('--write-exif', '-w', action='store_true',
                           help='同时写入 EXIF 元数据')
    p_organize.add_argument('-y', '--yes', action='store_true',
                           help='跳过确认提示')
    p_organize.set_defaults(ebird=True)
    
    # ===== 重置目录命令 =====
    p_reset = subparsers.add_parser('reset', help='恢复原始目录结构')
    p_reset.add_argument('directory', help='照片目录路径')
    p_reset.add_argument('-y', '--yes', action='store_true',
                        help='跳过确认提示')
    
    # ===== 列出国家命令 =====
    p_list = subparsers.add_parser('list-countries', help='列出支持的国家代码')
    
    # 解析参数
    args = parser.parse_args()
    
    # 如果没有指定命令但有位置参数，默认为 identify
    if args.command is None:
        if len(sys.argv) > 1 and not sys.argv[1].startswith('-'):
            # 检查第一个参数是否像文件路径
            first_arg = sys.argv[1]
            if os.path.exists(first_arg) or '*' in first_arg or '?' in first_arg or first_arg.endswith(('.jpg', '.jpeg', '.png', '.nef', '.arw', '.cr2', '.cr3')):
                # 重新解析为 identify 命令
                sys.argv.insert(1, 'identify')
                args = parser.parse_args()
            else:
                parser.print_help()
                return 1
        else:
            parser.print_help()
            return 1
    
    # 执行命令
    if args.command == 'identify':
        return cmd_identify(args)
    elif args.command == 'organize':
        return cmd_organize(args)
    elif args.command == 'reset':
        return cmd_reset(args)
    elif args.command == 'list-countries':
        return cmd_list_countries(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())

