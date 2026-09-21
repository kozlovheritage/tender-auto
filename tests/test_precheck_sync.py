from tendercore.analysis.precheck import check_title

def test_sync_fish():
    assert check_title("Поставка продуктов питания (Рыба свежемороженая и кальмары)")

def test_sync_pipe_electro():
    assert check_title("Приобретение электросварной трубы")

def test_sync_pipe_poly():
    assert check_title("Поставка полиэтиленовых труб")

def test_sync_pipe_foreign_excluded():
    # иностранный бренд → НЕ стоп (паритет с PIPE_EXCLUDE монолита)
    assert check_title("Поставка полиэтиленовых труб Rehau") is None