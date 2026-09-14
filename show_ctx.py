lines = open('make_product_v2.py', encoding='utf-8').readlines()
for i in range(8, 35):
    print(f'{i+1}: {lines[i]}', end='')