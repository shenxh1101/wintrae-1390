import click

from photo_organizer import __version__
from photo_organizer.commands.import_cmd import import_cmd
from photo_organizer.commands.rename_cmd import rename_cmd
from photo_organizer.commands.select_cmd import select_cmd
from photo_organizer.commands.watermark_cmd import watermark_cmd
from photo_organizer.commands.pack_cmd import pack_cmd
from photo_organizer.commands.report_cmd import report_cmd
from photo_organizer.commands.preset_cmd import preset_cmd
from photo_organizer.commands.delivery_cmd import delivery_cmd
from photo_organizer.commands.verify_cmd import verify_cmd
from photo_organizer.commands.archive_cmd import archive_cmd


@click.group()
@click.version_option(version=__version__, prog_name='photo')
@click.help_option('-h', '--help')
def main():
    """摄影师批量整理活动照片交付工具

    提供完整的活动照片交付流程：
      delivery  - 一键完整流程（import→rename→select→watermark→pack→report）
      import    - 按拍摄日期和相机编号导入照片
      rename    - 依据客户名、场次、序号批量重命名
      select    - 读取星标或手动清单筛选精修图
      watermark - 统一加水印、生成缩略图、按横竖构图分类
      pack      - 打包交付压缩包（含统一校验和 manifest）
      verify    - 验证压缩包和照片完整性（改动/缺失/多余）
      report    - 输出照片数量、缺失编号、重复文件和交付清单
      preset    - 管理预设配置，保存常用参数
      archive   - 归档项目文件，避免多个活动混在一起
    """
    pass


main.add_command(import_cmd, name='import')
main.add_command(rename_cmd, name='rename')
main.add_command(select_cmd, name='select')
main.add_command(watermark_cmd, name='watermark')
main.add_command(pack_cmd, name='pack')
main.add_command(report_cmd, name='report')
main.add_command(preset_cmd, name='preset')
main.add_command(delivery_cmd, name='delivery')
main.add_command(verify_cmd, name='verify')
main.add_command(archive_cmd, name='archive')


if __name__ == '__main__':
    main()
