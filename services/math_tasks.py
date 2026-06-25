from __future__ import annotations

import math
import re


DEFAULT_CRITERIA = (
    "Критерии: выбран корректный метод; записаны основные преобразования; вычисления выполнены без ошибок; "
    "ответ указан отдельно. Для развёрнутых задач дополнительно оцениваются обоснование, проверка ограничений "
    "и аккуратность оформления."
)

DIFFICULTY_BY_VARIANT = {
    1: "базовый",
    2: "средний",
    3: "повышенный",
    4: "сложный",
    5: "повышенный",
}


def build_math_task(
    exam_type: str,
    number: int,
    section_title: str,
    topic_title: str,
    topic_index: int = 1,
    variant: int = 1,
    shift: int = 0,
) -> dict[str, str]:
    """Create a deterministic author-course task close to OGE/EGE exam formats."""
    section = _clean_section_title(section_title)
    topic = topic_title or section
    normalized_variant = ((variant - 1) % 5) + 1
    if exam_type == "ЕГЭ":
        return _build_ege_task(number, section, topic, topic_index, normalized_variant, shift)
    return _build_oge_task(number, section, topic, topic_index, normalized_variant, shift)


def format_math_answer(value: float | int | str) -> str:
    if isinstance(value, str):
        return value
    number = float(value)
    if abs(number - round(number)) < 1e-9:
        return str(int(round(number)))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def make_wrong_answer(answer: str) -> str:
    try:
        value = float(str(answer).replace(",", "."))
    except (TypeError, ValueError):
        return "0"
    return format_math_answer(value + 1)


def _build_oge_task(number: int, section: str, topic: str, topic_index: int, variant: int, shift: int) -> dict[str, str]:
    lower = f"{section} {topic}".lower()
    difficulty = DIFFICULTY_BY_VARIANT[variant]
    base = topic_index + number + shift

    if _has(lower, "числ", "дроб", "степ", "корн", "вычисл", "рациональ", "процент"):
        if variant == 1:
            a, b, c = 2 + topic_index, 3 + number % 4, 5 + topic_index
            answer = a / b + c / (2 * b)
            return _task(
                f"Вычислите значение выражения {a}/{b} + {c}/{2*b}. Ответ запишите десятичной дробью или обыкновенной дробью.",
                answer,
                "Приведите дроби к общему знаменателю, сложите числители и при необходимости переведите результат в десятичную дробь.",
                difficulty,
            )
        if variant == 2:
            price = 1200 + 80 * base
            discount = 12 + topic_index
            answer = price * (100 - discount) / 100
            return _task(
                f"Цена набора для подготовки к экзамену равна {price} рублей. Во время акции цену снизили на {discount}%. Сколько рублей стоит набор после скидки?",
                answer,
                "Скидка p% означает умножение исходной цены на коэффициент (100-p)/100.",
                difficulty,
            )
        if variant == 3:
            n = 3 + topic_index
            answer = n * n - 2 * n
            return _task(
                f"Найдите значение выражения sqrt({n*n}) · (sqrt({n*n}) - 2).",
                answer,
                "Сначала вычислите значение квадратного корня, затем выполните действия в скобках и умножение.",
                difficulty,
            )
        if variant == 4:
            a, b = 2 + topic_index, 3 + number
            answer = a**3 * b**2
            return _task(
                f"Упростите выражение ({a}^2 · {b}) · ({a} · {b}) и найдите его значение.",
                answer,
                "Используйте правило умножения степеней с одинаковым основанием: a^m · a^n = a^(m+n).",
                difficulty,
            )
        value = 37.5 + 2.5 * topic_index
        answer = round(value / 5) * 5
        return _task(
            f"Результат измерения равен {format_math_answer(value)}. Округлите его до ближайшего числа, кратного 5.",
            answer,
            "Сравните расстояние до соседних чисел, кратных 5, и выберите ближайшее.",
            difficulty,
        )

    if _has(lower, "алгеб", "многочлен", "сокращ", "дробн", "одночлен", "одз"):
        x = 2 + topic_index
        if variant == 1:
            answer = (x + 3) * (x - 3)
            return _task(
                f"Найдите значение выражения (x + 3)(x - 3) при x = {x}.",
                answer,
                "Используйте формулу разности квадратов или сначала раскройте скобки: x^2 - 9.",
                difficulty,
            )
        if variant == 2:
            answer = 2 * x + 7
            return _task(
                f"Упростите выражение 3(2x - 1) - 4(x - 2) и найдите его значение при x = {x}.",
                answer,
                "Раскройте скобки, приведите подобные слагаемые и подставьте значение переменной.",
                difficulty,
            )
        if variant == 3:
            a = 5 + topic_index
            answer = a + 4
            return _task(
                f"Сократите дробь (a^2 - 16)/(a - 4) и найдите её значение при a = {a}.",
                answer,
                "Разложите числитель как разность квадратов: a^2 - 16 = (a - 4)(a + 4), затем сократите общий множитель.",
                difficulty,
            )
        if variant == 4:
            answer = x - 5
            return _task(
                f"Преобразуйте выражение (x^2 - 25)/(x + 5) и найдите значение при x = {x}. Укажите, почему x не может быть равен -5.",
                answer,
                "Разложите числитель на множители и сократите дробь, отдельно записав ограничение знаменателя.",
                difficulty,
            )
        answer = x + 2
        return _task(
            f"Упростите выражение (sqrt({x*x}) + 2) при x > 0.",
            answer,
            "При положительном x выполняется sqrt(x^2)=x, поэтому выражение равно x+2.",
            difficulty,
        )

    if _has(lower, "урав", "нерав", "систем"):
        if variant == 1:
            x = 4 + topic_index
            a = 3 + number % 3
            b = 7 + topic_index
            right = a * x - b
            return _task(f"Решите уравнение {a}x - {b} = {right}.", x, "Перенесите свободный член вправо и разделите на коэффициент при x.", difficulty)
        if variant == 2:
            r1, r2 = 2 + topic_index, 5 + topic_index
            s, p = r1 + r2, r1 * r2
            return _task(
                f"Решите квадратное уравнение x^2 - {s}x + {p} = 0. В ответ запишите меньший корень.",
                min(r1, r2),
                "Найдите корни через дискриминант или по теореме Виета; затем выберите меньший.",
                difficulty,
            )
        if variant == 3:
            x, y = 3 + topic_index, 2 + number
            return _task(
                f"Решите систему: x + y = {x+y}; 2x - y = {2*x-y}. В ответ запишите x.",
                x,
                "Выразите y из первого уравнения и подставьте во второе либо сложите уравнения после преобразования.",
                difficulty,
            )
        if variant == 4:
            border = 2 + topic_index
            return _task(
                f"Найдите наименьшее целое решение неравенства (x - {border})(x + {border+1}) > 0.",
                border + 1,
                "Отметьте нули множителей на числовой прямой и выберите промежутки, где произведение положительно.",
                difficulty,
            )
        x = 4 + topic_index
        denominator = x - 1
        return _task(
            f"Решите дробно-рациональное уравнение (x + 2)/(x - 1) = {(x+2)/denominator:.2f}. В ответ запишите x.",
            x,
            "Укажите ОДЗ x != 1, затем умножьте обе части на знаменатель и решите линейное уравнение.",
            difficulty,
        )

    if _has(lower, "функц", "граф"):
        k = 1 + (base % 4)
        b = variant + 1
        if variant == 1:
            return _task(f"Функция задана формулой y = {k}x + {b}. Найдите y при x = 5.", 5 * k + b, "Подставьте x=5 в формулу функции.", difficulty)
        if variant == 2:
            y = k * 4 + b
            return _task(f"График линейной функции проходит через точки (0; {b}) и (4; {y}). Найдите коэффициент k.", k, "Коэффициент k равен отношению изменения y к изменению x.", difficulty)
        if variant == 3:
            a = 1
            xv = 2 + topic_index
            c = variant
            return _task(
                f"Квадратичная функция имеет вид y = x^2 - {2*xv}x + {xv*xv+c}. Найдите абсциссу вершины параболы.",
                xv,
                "Для функции ax^2+bx+c абсцисса вершины равна -b/(2a).",
                difficulty,
            )
        if variant == 4:
            x = 2 + topic_index
            return _task(f"Функция y = {k}/x задана при x != 0. Найдите значение y при x = {x}.", k / x, "Подставьте значение x в формулу обратной пропорциональности.", difficulty)
        return _task(
            f"На графике функции y = kx - 3 точка A({topic_index + 2}; {k*(topic_index+2)-3}) принадлежит графику. Найдите k.",
            k,
            "Подставьте координаты точки в формулу и выразите k.",
            difficulty,
        )

    if _has(lower, "практи", "тариф", "покуп", "таблиц", "ремонт", "поезд", "план"):
        if variant == 1:
            fixed, per = 350 + 20 * topic_index, 12 + number
            minutes = 80 + 5 * topic_index
            return _task(f"Тариф включает абонентскую плату {fixed} рублей и {per} рублей за минуту сверх пакета. За месяц израсходовано {minutes} минут сверх пакета. Найдите итоговую сумму.", fixed + per * minutes, "Сложите фиксированную плату и стоимость дополнительных минут.", difficulty)
        if variant == 2:
            packs, price = 7 + topic_index, 180 + 15 * number
            discount = 10 + topic_index
            return _task(f"Для ремонта купили {packs} упаковок плитки по {price} рублей. На покупку действует скидка {discount}%. Сколько рублей заплатили?", packs * price * (100 - discount) / 100, "Найдите стоимость без скидки и умножьте на коэффициент после скидки.", difficulty)
        if variant == 3:
            speed = 60 + 5 * topic_index
            time = 2.5
            return _task(f"Автомобиль ехал {time} часа со средней скоростью {speed} км/ч. Сколько километров он проехал?", speed * time, "Используйте формулу S = v · t.", difficulty)
        if variant == 4:
            length, width = 5 + topic_index, 4 + number % 3
            tile_area = 0.25
            return _task(f"Комната имеет размеры {length} м на {width} м. Одна упаковка покрытия закрывает {tile_area} м². Сколько упаковок потребуется?", math.ceil(length * width / tile_area), "Найдите площадь комнаты и разделите на площадь, закрываемую одной упаковкой; результат округлите вверх.", difficulty)
        return _task(f"В таблице указаны результаты: 12, {14+topic_index}, {16+number}, {18+variant}. Найдите среднее значение.", (12 + 14 + topic_index + 16 + number + 18 + variant) / 4, "Сложите все значения и разделите сумму на количество значений.", difficulty)

    if _has(lower, "геометр", "треуг", "четыр", "окруж", "площад", "угл"):
        if variant == 1:
            a, b = 6 + topic_index, 8 + topic_index
            return _task(f"Катеты прямоугольного треугольника равны {a} и {b}. Найдите квадрат гипотенузы.", a * a + b * b, "По теореме Пифагора c^2 = a^2 + b^2.", difficulty)
        if variant == 2:
            base, height = 8 + topic_index, 5 + number % 5
            return _task(f"Основание треугольника равно {base}, высота к нему равна {height}. Найдите площадь треугольника.", base * height / 2, "Площадь треугольника равна половине произведения основания на высоту.", difficulty)
        if variant == 3:
            angle = 40 + 5 * topic_index
            return _task(f"Вписанный угол, опирающийся на дугу окружности, равен {angle}°. Найдите градусную меру этой дуги.", 2 * angle, "Вписанный угол равен половине дуги, на которую он опирается.", difficulty)
        if variant == 4:
            k, side = 2 + topic_index % 3, 5 + number
            return _task(f"Стороны подобных треугольников относятся как 1:{k}. Меньшая соответствующая сторона равна {side}. Найдите большую сторону.", k * side, "В подобных фигурах соответствующие стороны пропорциональны коэффициенту подобия.", difficulty)
        return _task(f"В параллелограмме основание равно {7+topic_index}, высота к нему равна {4+variant}. Найдите площадь.", (7 + topic_index) * (4 + variant), "Площадь параллелограмма равна произведению основания на высоту.", difficulty)

    if _has(lower, "вероят", "статист", "средн", "медиан", "частот", "диаграм"):
        if variant == 1:
            good, total = 3 + topic_index, 12 + number
            return _task(f"В наборе {total} карточек, из них {good} с заданиями по геометрии. Найдите вероятность выбрать такую карточку.", good / total, "Разделите число благоприятных исходов на общее число исходов.", difficulty)
        if variant == 2:
            values = [10, 12 + topic_index, 14 + number % 4, 18]
            return _task(f"Найдите среднее арифметическое чисел {', '.join(map(str, values))}.", sum(values) / len(values), "Сумму чисел разделите на их количество.", difficulty)
        if variant == 3:
            values = sorted([7, 9 + topic_index, 10 + number % 3, 12, 15])
            return _task(f"Найдите медиану набора данных: {', '.join(map(str, values))}.", values[len(values)//2], "Для нечётного количества значений медиана — центральный элемент упорядоченного ряда.", difficulty)
        if variant == 4:
            success, fail = 8 + topic_index, 12 + number
            return _task(f"В таблице частот событие A произошло {success} раз, не произошло {fail} раз. Найдите относительную частоту события A.", success / (success + fail), "Относительная частота равна числу наступлений события, делённому на число всех испытаний.", difficulty)
        return _task(f"Из 6 вариантов контрольной два содержат задачу на вероятность. Ученик получает два разных варианта. Найдите вероятность, что оба варианта содержат такую задачу.", "1/15", "Используйте классическую вероятность: C(2,2)/C(6,2)=1/15.", difficulty)

    if _has(lower, "текст", "движ", "работ", "смес", "совмест"):
        if variant in {1, 5}:
            speed1, speed2 = 48 + topic_index, 60 + number
            time = 2
            return _task(f"Два автомобиля выехали навстречу друг другу. Скорости равны {speed1} км/ч и {speed2} км/ч. Какое расстояние между ними было сначала, если они встретились через {time} часа?", (speed1 + speed2) * time, "При движении навстречу скорости складываются, расстояние равно суммарной скорости, умноженной на время.", difficulty)
        if variant == 2:
            first, second = 6 + topic_index, 12 + 2 * topic_index
            return _task(f"Один мастер выполняет работу за {first} часов, другой — за {second} часов. За сколько часов они выполнят работу вместе?", first * second / (first + second), "Сложите производительности 1/first и 1/second, затем найдите обратную величину.", difficulty)
        if variant == 3:
            mass, percent = 40 + topic_index, 15 + number % 5
            return _task(f"В растворе массой {mass} кг содержится {percent}% соли. Сколько килограммов соли в растворе?", mass * percent / 100, "Масса вещества равна массе раствора, умноженной на массовую долю.", difficulty)
        cost, growth = 5000 + 200 * topic_index, 8 + variant
        return _task(f"Сумма на счёте увеличилась на {growth}% и стала равна {format_math_answer(cost*(100+growth)/100)} рублей. Какой была сумма до увеличения?", cost, "Разделите конечную сумму на коэффициент роста.", difficulty)

    return _task(f"Решите задание по теме «{topic}»: найдите значение выражения ({10+base} + {3+variant}) · {2+topic_index%3}.", (10 + base + 3 + variant) * (2 + topic_index % 3), "Выполните действия в скобках, затем умножение.", difficulty)


def _build_ege_task(number: int, section: str, topic: str, topic_index: int, variant: int, shift: int) -> dict[str, str]:
    lower = f"{section} {topic}".lower()
    difficulty = DIFFICULTY_BY_VARIANT[variant] if variant < 4 else "сложный"
    base = number + topic_index + shift

    if _has(lower, "планиметр", "треуг", "окруж", "площад", "угл", "подоб", "координат"):
        if variant == 1:
            a, h = 10 + topic_index, 6 + number % 4
            return _task(f"В треугольнике основание равно {a}, высота к нему равна {h}. Найдите площадь.", a * h / 2, "Используйте формулу площади треугольника S = ah/2.", difficulty)
        if variant == 2:
            angle = 35 + 5 * topic_index
            return _task(f"Вписанный угол равен {angle}°. Найдите центральный угол, опирающийся на ту же дугу.", 2 * angle, "Центральный угол в два раза больше вписанного, опирающегося на ту же дугу.", difficulty)
        if variant == 3:
            k, side = 3, 4 + topic_index
            return _task(f"Площади подобных треугольников относятся как 1:{k*k}. Сторона меньшего треугольника равна {side}. Найдите соответствующую сторону большего.", k * side, "Отношение площадей равно квадрату коэффициента подобия.", difficulty)
        if variant == 4:
            return _task(f"Точки A(0;0), B({3+topic_index};0), C(0;{4+topic_index}) образуют треугольник. Найдите квадрат длины гипотенузы BC.", (3+topic_index)**2 + (4+topic_index)**2, "Используйте формулу расстояния между точками или теорему Пифагора.", difficulty)
        return _task(f"Радиус окружности равен {5+topic_index}. Найдите площадь круга, делённую на pi.", (5 + topic_index) ** 2, "Площадь круга S = pi*r^2, поэтому S/pi = r^2.", difficulty)

    if _has(lower, "стерео", "призм", "пирам", "цилиндр", "конус", "шар", "простран"):
        if variant == 1:
            a, h = 4 + topic_index, 8 + number % 5
            return _task(f"Основание прямой призмы — квадрат со стороной {a}. Высота призмы равна {h}. Найдите объём.", a * a * h, "Объём призмы равен площади основания, умноженной на высоту.", difficulty)
        if variant == 2:
            s, h = 9 + topic_index, 6 + number % 4
            return _task(f"Площадь основания пирамиды равна {s}, высота равна {h}. Найдите объём пирамиды.", s * h / 3, "Объём пирамиды равен одной трети произведения площади основания на высоту.", difficulty)
        if variant == 3:
            r, h = 3 + topic_index, 7 + number % 3
            return _task(f"Радиус цилиндра равен {r}, высота равна {h}. Найдите объём цилиндра, делённый на pi.", r * r * h, "Объём цилиндра V = pi*r^2*h.", difficulty)
        if variant == 4:
            r = 2 + topic_index
            return _task(f"Радиус шара равен {r}. Найдите площадь поверхности шара, делённую на pi.", 4 * r * r, "Площадь поверхности шара S = 4*pi*r^2.", difficulty)
        return _task(f"В прямоугольном параллелепипеде рёбра равны {3+topic_index}, {4+topic_index} и {5+topic_index}. Найдите квадрат пространственной диагонали.", (3+topic_index)**2 + (4+topic_index)**2 + (5+topic_index)**2, "Квадрат диагонали равен сумме квадратов трёх измерений.", difficulty)

    if _has(lower, "вероят", "статист", "комбин", "независ", "данн"):
        if variant == 1:
            good, total = 5 + topic_index, 20 + number
            return _task(f"Из {total} выпускников {good} выбрали профильную математику. Найдите вероятность случайно выбрать такого выпускника.", good / total, "Вероятность равна отношению благоприятных исходов к общему числу исходов.", difficulty)
        if variant == 2:
            p1, p2 = 0.4, 0.5 + 0.05 * (topic_index % 3)
            return _task(f"Вероятности двух независимых событий равны {format_math_answer(p1)} и {format_math_answer(p2)}. Найдите вероятность наступления обоих событий.", p1 * p2, "Для независимых событий вероятности перемножаются.", difficulty)
        if variant == 3:
            return _task("Вероятность сдать первый тест равна 0,8. Если первый тест сдан, вероятность сдать второй равна 0,75. Найдите вероятность сдать оба теста.", 0.6, "Используйте правило умножения условных вероятностей: 0,8*0,75.", difficulty)
        if variant == 4:
            values = [62, 70 + topic_index, 74, 86 + number % 4, 90]
            return _task(f"По данным тренировок баллы равны {', '.join(map(str, values))}. Найдите размах набора.", max(values) - min(values), "Размах равен разности максимального и минимального значения.", difficulty)
        return _task("В коробке 4 красных и 6 синих карточек. Дважды без возвращения достают карточку. Найдите вероятность, что обе карточки красные.", "2/15", "Вероятность равна 4/10 * 3/9 = 2/15.", difficulty)

    if _has(lower, "урав", "логариф", "показат", "иррацион", "тригонометрические уравнения"):
        if "логариф" in lower or variant == 3:
            n = 3 + topic_index % 3
            return _task(f"Решите уравнение log_2(x - 1) = {n}.", 2**n + 1, "По определению логарифма x-1=2^n, затем найдите x и проверьте ОДЗ.", difficulty)
        if "тригоном" in lower or variant == 4:
            return _task("Решите уравнение sin x = 1/2 на отрезке [0; pi]. В ответ запишите количество корней.", 2, "На указанном отрезке подходят x=pi/6 и x=5pi/6.", difficulty)
        if variant == 2:
            x = 2 + topic_index
            return _task(f"Решите иррациональное уравнение sqrt(x + {x*x-x}) = {x}.", x, "Возведите обе части в квадрат и проверьте найденный корень.", difficulty)
        power = 2 + topic_index % 4
        return _task(f"Решите уравнение 3^(x - 1) = {3**power}.", power + 1, "Представьте правую часть как степень тройки и приравняйте показатели.", difficulty)

    if _has(lower, "нерав", "интервал"):
        if variant == 1:
            border = 4 + topic_index
            return _task(f"Найдите наименьшее целое решение неравенства 3x - {3*border-1} > 0.", border, "Решите линейное неравенство и выберите наименьшее целое решение.", difficulty)
        if variant == 2:
            a, b = 2 + topic_index, 6 + topic_index
            return _task(f"Решите неравенство (x - {a})(x - {b}) <= 0. В ответ запишите длину промежутка решений.", b - a, "По методу интервалов решение находится между корнями включительно.", difficulty)
        if variant == 3:
            n = 3 + topic_index
            return _task(f"Найдите наименьшее целое решение неравенства 2^x >= {2**n}.", n, "При основании больше 1 сравните показатели степеней.", difficulty)
        if variant == 4:
            n = 2 + topic_index % 3
            return _task(f"Решите неравенство log_2(x) > {n}. В ответ запишите наименьшее целое решение.", 2**n + 1, "По определению логарифма x > 2^n; учитывается ОДЗ x>0.", difficulty)
        return _task(f"Найдите число целых решений системы неравенств: x > {topic_index}; x <= {topic_index+5}.", 5, "Пересеките промежутки и посчитайте целые числа.", difficulty)

    if _has(lower, "производ", "первообраз", "касатель", "монотон", "экстрем"):
        if variant == 1:
            a, x = 3 + topic_index, 2 + number % 3
            return _task(f"Функция f(x)=x^2+{a}x. Найдите f'({x}).", 2 * x + a, "Производная равна f'(x)=2x+a; подставьте указанное x.", difficulty)
        if variant == 2:
            x0, b = 2 + topic_index, 5 + number
            return _task(f"К графику функции f(x)=x^2+{b} проведена касательная в точке x0={x0}. Найдите угловой коэффициент касательной.", 2 * x0, "Угловой коэффициент касательной равен значению производной в точке.", difficulty)
        if variant == 3:
            a = 3 + topic_index
            return _task(f"Функция f(x)=x^3-{3*a}x. Найдите положительную точку экстремума.", math.sqrt(a), "Найдите f'(x)=3x^2-3a, приравняйте к нулю и выберите положительный корень.", difficulty)
        if variant == 4:
            return _task(f"Найдите длину промежутка убывания функции f(x)=x^2-{2*(4+topic_index)}x+1.", "бесконечный", "Парабола убывает на промежутке (-∞; x0), где x0 — абсцисса вершины.", difficulty)
        return _task(f"Первообразная функции f(x)=2x+{topic_index} имеет вид F(x)=x^2+{topic_index}x+C. Найдите F(1)-F(0).", 1 + topic_index, "Подставьте значения в любую первообразную; константа сократится.", difficulty)

    if _has(lower, "тригоном"):
        if variant == 1:
            return _task("Найдите значение выражения 2sin30° + cos60°.", 1.5, "Используйте sin30°=1/2 и cos60°=1/2.", difficulty)
        if variant == 2:
            return _task("Упростите выражение sin^2 x + cos^2 x. В ответ запишите полученное число.", 1, "Используйте основное тригонометрическое тождество.", difficulty)
        if variant == 3:
            return _task("Решите уравнение cos x = 0 на отрезке [0; 2pi]. В ответ запишите количество корней.", 2, "На отрезке подходят x=pi/2 и x=3pi/2.", difficulty)
        if variant == 4:
            return _task("Сколько корней уравнения sin x = sqrt(3)/2 на отрезке [0; 2pi]?", 2, "На полном периоде синус принимает это значение в двух точках.", difficulty)
        return _task("Найдите tg45° + ctg45°.", 2, "tg45°=1 и ctg45°=1.", difficulty)

    if _has(lower, "параметр"):
        if variant == 1:
            root = 2 + topic_index
            right = 10 + number
            return _task(f"Найдите a, если x={root} является корнем уравнения x+a={right}.", right - root, "Подставьте x и выразите параметр.", difficulty)
        if variant == 2:
            return _task(f"При каких a уравнение x^2-2x+a=0 имеет один корень? В ответ запишите a.", 1, "Один корень у квадратного уравнения при D=0.", difficulty)
        if variant == 3:
            a = 3 + topic_index
            return _task(f"Найдите значение параметра a, при котором прямые y={a}x+1 и y=ax+5 параллельны. В ответ запишите количество таких a.", "любое", "Прямые с одинаковым коэффициентом при x параллельны при любом a, если свободные члены различны.", difficulty)
        if variant == 4:
            return _task("Найдите все a, при которых уравнение |x|=a имеет два различных корня. В ответ запишите условие.", "a>0", "Модульное уравнение имеет два корня, если правая часть положительна.", difficulty)
        return _task(f"Найдите количество целых a, при которых уравнение x^2+a=0 имеет действительные корни и -5 <= a <= 5.", 6, "Нужны a <= 0; на заданном промежутке это -5,-4,-3,-2,-1,0.", difficulty)

    if _has(lower, "эконом", "кредит", "вклад", "платеж", "процент"):
        if variant == 1:
            s, p = 100000 + 5000 * topic_index, 10 + number % 5
            return _task(f"Вклад {s} рублей увеличился на {p}%. Найдите сумму после начисления процентов.", s * (100 + p) / 100, "Умножьте исходную сумму на коэффициент роста.", difficulty)
        if variant == 2:
            s, p = 200000 + 10000 * topic_index, 12
            return _task(f"Кредит {s} рублей уменьшается одним платежом после начисления {p}%. Какой платёж нужен, чтобы закрыть долг полностью?", s * 1.12, "После начисления процентов долг равен S*(1+p/100).", difficulty)
        if variant == 3:
            s = 120000 + 5000 * topic_index
            return _task(f"Вклад два года подряд увеличивали на 10%. Найдите итоговую сумму при начальной сумме {s} рублей.", s * 1.21, "Два последовательных увеличения на 10% дают коэффициент 1,1^2=1,21.", difficulty)
        if variant == 4:
            s = 300000 + 10000 * topic_index
            return _task(f"После первого года долг {s} рублей вырос на 15%, затем был внесён платёж 50000 рублей. Найдите остаток долга.", s * 1.15 - 50000, "Сначала начислите проценты, затем вычтите платёж.", difficulty)
        return _task(f"Цена курса сначала выросла на 20%, затем снизилась на 20% и стала {9600 + 200*topic_index} рублей. Найдите исходную цену.", (9600 + 200 * topic_index) / 0.96, "Последовательные изменения дают коэффициент 1,2*0,8=0,96.", difficulty)

    if _has(lower, "текст", "движ", "работ", "смес", "сплав"):
        if variant == 1:
            v1, v2, t = 70 + topic_index, 50 + number, 3
            return _task(f"Два поезда движутся навстречу со скоростями {v1} и {v2} км/ч. Они встретились через {t} часа. Найдите начальное расстояние.", (v1 + v2) * t, "При движении навстречу скорости складываются.", difficulty)
        if variant == 2:
            a, b = 8 + topic_index, 12 + topic_index
            return _task(f"Один насос наполняет бассейн за {a} часов, второй — за {b} часов. За сколько часов они наполнят бассейн вместе?", a * b / (a + b), "Сложите производительности насосов.", difficulty)
        if variant == 3:
            mass, percent = 60 + topic_index, 20
            return _task(f"Имеется {mass} кг {percent}%-го раствора. Сколько кг вещества содержится в растворе?", mass * percent / 100, "Масса вещества равна массе раствора, умноженной на долю вещества.", difficulty)
        if variant == 4:
            return _task("Катер прошёл 30 км по течению и 20 км против течения. Скорость катера в стоячей воде 12 км/ч, скорость течения 2 км/ч. Найдите общее время пути.", 30 / 14 + 20 / 10, "По течению скорость складывается, против течения вычитается.", difficulty)
        return _task(f"Рабочий планировал выполнить {100+10*topic_index} деталей, но каждый день делал на 5 деталей больше и закончил на 2 дня раньше. В ответ запишите уравнение для плановой дневной нормы x.", f"({100+10*topic_index})/x - ({100+10*topic_index})/(x+5)=2", "Сравните плановое и фактическое время выполнения работы.", difficulty)

    return _task(f"Решите задание профильного уровня по теме «{topic}»: найдите значение выражения ({12+base})^2 - ({10+base})^2.", (12 + base) ** 2 - (10 + base) ** 2, "Используйте формулу разности квадратов.", difficulty)


def _task(condition: str, answer: float | int | str, solution: str, difficulty: str, criteria: str | None = None) -> dict[str, str]:
    return {
        "condition_text": condition,
        "correct_answer": format_math_answer(answer),
        "solution_explanation": solution,
        "criteria": criteria or DEFAULT_CRITERIA,
        "difficulty": difficulty,
    }


def _has(text: str, *parts: str) -> bool:
    return any(part in text for part in parts)


def _clean_section_title(section_title: str) -> str:
    return re.sub(r"^Модуль\s+\d+\.\s*", "", section_title or "").strip()
