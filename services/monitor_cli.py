#!/usr/bin/env python3
import argparse
import sys

from core.logger import get_logger
from services.email_scanner import EmailScanner
from services.monitor import CreditMonitor
from services.subscription_checker import SubscriptionChecker

logger = get_logger('monitor_cli')


def main() -> None:
    parser = argparse.ArgumentParser(
        description='多项目余额监控工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                          # 检查所有启用的项目
  %(prog)s --project "项目A"        # 检查指定项目
  %(prog)s --dry-run                # 测试模式，不发送告警
  %(prog)s --config custom.json     # 使用自定义配置文件
  %(prog)s --check-subscriptions    # 检查订阅续费提醒
  %(prog)s --check-email            # 扫描邮箱告警邮件
  %(prog)s --check-email --email-days 3  # 扫描最近3天的邮件
        """
    )

    parser.add_argument(
        '--config',
        default='config.json',
        help='配置文件路径 (默认: config.json)'
    )

    parser.add_argument(
        '--project',
        help='指定要检查的项目名称'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='测试模式，只显示余额不发送告警'
    )

    parser.add_argument(
        '--check-subscriptions',
        action='store_true',
        help='检查订阅续费提醒'
    )

    parser.add_argument(
        '--check-email',
        action='store_true',
        help='扫描邮箱告警邮件'
    )

    parser.add_argument(
        '--email-days',
        type=int,
        default=1,
        help='扫描最近几天的邮件 (默认: 1天)'
    )

    args = parser.parse_args()

    try:
        monitor = CreditMonitor(args.config)
        monitor.run(project_name=args.project, dry_run=args.dry_run)

        if args.check_subscriptions or args.project is None:
            subscription_checker = SubscriptionChecker(args.config)
            subscription_checker.check_subscriptions(dry_run=args.dry_run)

        if args.check_email:
            email_scanner = EmailScanner(args.config)
            email_scanner.scan_emails(days=args.email_days, dry_run=args.dry_run)
    except Exception as e:
        logger.error(f"错误: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()

