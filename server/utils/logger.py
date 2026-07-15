import os
import sys
import logging

class ColoredProcessFormatter(logging.Formatter):
    """
    로그 레벨 및 프로세스명에 따라 콘솔 출력 색상을 동적으로 매핑해 주는 표준 로깅 포맷터입니다.
    """
    # ANSI Color Escape Codes
    RESET = "\033[0m"
    BOLD = "\033[1m"
    
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    ORANGE = "\033[33m" # Bold Yellow/Orange

    # 프로세스별 기본 시그니처 색상 테이블
    PROCESS_COLORS = {
        "SERVER": GREEN,
        "WATCHER": CYAN,
        "CHAIN": MAGENTA,
        "SCHEDULER": YELLOW,
        "GRAPHSYNC": CYAN
    }

    def __init__(self, fmt=None, datefmt=None, process_name="SYSTEM"):
        super().__init__(fmt, datefmt)
        self.process_name = process_name.upper()
        # 프로세스 시그니처 색상 획득
        self.proc_color = self.PROCESS_COLORS.get(self.process_name, self.RESET)

    def format(self, record):
        # 1. 원본 메시지 빌드
        orig_msg = super().format(record)
        
        # 2. 로그 레벨에 따른 동적 컬러 결정
        level = record.levelno
        
        if level >= logging.ERROR:
            # 에러 및 치명 오류는 강렬한 밝은 빨간색으로 통일 강조
            color_prefix = f"{self.RED}{self.BOLD}"
        elif level == logging.WARNING:
            # 경고는 주황색으로 강조
            color_prefix = f"{self.ORANGE}{self.BOLD}"
        else:
            # 정상 수준(INFO, DEBUG)은 프로세스 고유 시그니처 색상 적용
            color_prefix = self.proc_color
            
        return f"{color_prefix}{orig_msg}{self.RESET}"

def get_process_logger(process_name: str, log_filename: str) -> logging.Logger:
    """
    공통 로깅 규격을 따르며, 프로세스별 고유 컬러(ANSI) 스트림 핸들러와
    깨끗한 Plain-Text 파일 핸들러가 결합된 전용 Logger 인스턴스를 반환합니다.
    """
    # 루트 로거에 등록된 기본 핸들러 소거 (타 모듈의 basicConfig 오염 차단)
    root_logger = logging.getLogger()
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    logger = logging.getLogger(process_name)
    logger.setLevel(logging.INFO)
    
    logger.propagate = True # 자식 모듈들의 로깅 전파를 부모 로거로 허용
    
    # 기존에 등록된 핸들러가 있으면 클리어하여 오작동 방지
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        
    log_format = '[%(name)s] [%(asctime)s] %(levelname)s - %(message)s'
    
    # 1. 콘솔 핸들러 (동적 컬러 Formatter 장착)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColoredProcessFormatter(log_format, process_name=process_name))
    logger.addHandler(console_handler)
    
    # 2. 파일 핸들러 (ANSI 문자 없는 평문 Formatter 장착)
    server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_path = os.path.join(server_dir, log_filename)
    
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(file_handler)
    
    return logger
