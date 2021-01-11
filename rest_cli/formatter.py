import subprocess


def find_subclasses(cls):
    """
    Recursively find all subclasses of given class cls.
    """
    subclasses = cls.__subclasses__()
    for subclass in list(subclasses):
        subclasses.extend(find_subclasses(subclass))
    return list(set(subclasses))


class OutputFormatter:
    terminal = False

    def __init__(self, text):
        if type(text) == list:
            self.lines = text
        else:
            self.lines = text.splitlines()

    def __getattr__(self, name):
        cls = self.__class__
        cls = []
        if self.terminal:
            raise Exception('Unable to chain formatter "%s"; "%s" is terminal' % (
                name, cls.__name__.lower()
            ))
        while cls is not OutputFormatter:
            [cls.append(kls) for kls in cls.__bases__]
            if cls:
                cls = cls.pop()
            else:
                raise Exception("I'm lost and failed to find myself somehow.")
        for formatter in find_subclasses(cls):
            if formatter.__name__.lower() == name.lower():
                return formatter(self.lines[:])
        raise KeyError('formatter not found: %s' % name)

    def __str__(self):
        return '\n'.join(self.lines)


class Head(OutputFormatter):
    def __call__(self, n=10, c=None):
        if c:
            lines = []
            left = c
            for line in self.lines:
                if len(line) < left:
                    # clear to add the entire line
                    lines.append(line)
                else:
                    # append only whats remaining to be read
                    lines.append(line[:len(line) - left])
                left -= len(lines[-1])
                if left <= 0:
                    break
            self.lines = lines
        if n:
            self.lines = self.lines[:n]
        return self


class Tail(Head):
    def __call__(self, n=10, c=None):
        head = self.head
        head.lines.reverse()
        head(n, c)
        self.lines = head.lines
        self.lines.reverse()
        return self


if __name__ == '__main__':
    # testing...
    data = '1a\n2b\n3c\n4d\n5e\n6f\n7g\n8h\n9i\n10j\n11k\n'
    print('* first 3 lines')
    outf = OutputFormatter(data)
    print(outf.head(3))
    print('* 3rd line')
    print(Head(data)(3).tail(1))
    print('* last 3 lines')
    print(outf.tail(3))
    print('* 3rd to last lines')
    print(Tail(data)(3).head(1))
    print(outf.less())
