import click

from photo_organizer import __version__
from photo_organizer.commands.import_cmd import import_cmd
from photo_organizer.commands.rename_cmd import rename_cmd
from photo_organizer.commands.select_cmd import select_cmd
from photo_organizer.commands.watermark_cmd import watermark_cmd
from photo_organizer.commands.pack_cmd import pack_cmd
from photo_organizer.commands.report_cmd import report_cmd


@click.group()
@click.version_option(version=__version__, prog_name='photo')
@click.help_option('-h', '--help')
def main():
    """摄影师批量整理活动照片交付工具

    提供 import、rename、select、watermark、pack、report 六个命令，
    帮助摄影师高效整理和交付活动照片。
    """
    pass


main.add_command(import_cmd, name='import')
main.add_command(rename_cmd, name='rename')
main.add_command(select_cmd, name='select')
main.add_command(watermark_cmd, name='watermark')
main.add_command(pack_cmd, name='pack')
main.add_command(report_cmd, name='report')


if __name__ == '__main__':
    main()
