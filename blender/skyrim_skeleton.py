"""Parse an XPMSE <hkpackfile> skeleton.xml: names, parents, reference local TRS."""
import re, xml.etree.ElementTree as ET
def load_skeleton(path):
    root = ET.parse(path).getroot()
    sk = next(o for o in root.iter('hkobject') if o.get('class') == 'hkaSkeleton')
    p = {e.get('name'): e for e in sk.findall('hkparam')}
    parents = [int(x) for x in p['parentIndices'].text.split()]
    names = [b.find("hkparam[@name='name']").text for b in p['bones'].findall('hkobject')]
    nums = [float(x) for x in re.findall(r'[-+0-9.eE]+', p['referencePose'].text)]
    ref = [(nums[i*10:i*10+3], nums[i*10+3:i*10+7]) for i in range(len(names))]  # t, q(xyzw)
    return names, parents, ref
