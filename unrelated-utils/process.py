def main():
    with open('in.txt', 'r') as f:
        lines = f.readlines()

    file_out = open('out.txt', 'w')
    
    data = [line.strip('\n').split('\t') for line in lines]

    current_name = ''
    current_is_laosheng_valid = False

    for row in data:
        name = row[0]
        is_laosheng_valid = (row[1] == '1')

        # 列表中同一个名字可能出现1次或多次, 但只要有一次is_laosheng_valid为1, 就认为这个名字是有效的. 对每个名字, 只输出一次 "{name}\t{is_laosheng_valid}". 输入列表中名字是有序的, 即同一个名字若出现多次必然是连续出现的
        if name != current_name:
            if current_name != '':
                file_out.write(f'{current_name}\t\t初中/小学\t{'1' if current_is_laosheng_valid else ''}\n')
            current_name = name
            current_is_laosheng_valid = is_laosheng_valid
        else:
            current_is_laosheng_valid = current_is_laosheng_valid or is_laosheng_valid
    # 处理最后一个名字
    if current_name != '':
        file_out.write(f'{current_name}\t\t初中/小学\t{'1' if current_is_laosheng_valid else ''}\n')

    file_out.close()

if __name__ == '__main__':
    main()