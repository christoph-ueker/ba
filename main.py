import os
import subprocess
from helper import *
from uppaalpy import nta as u
import copy


# creates a new template from blank_template
def new_template(name):
    new = copy.deepcopy(blank_template)
    new.name = u.Name(name=name, pos=[0, 0])
    sys.templates.append(new)
    return new


class Event:
    def __init__(self, signal, origin, target, ts):
        # either Req or Ack
        self.signal = signal
        # either 0 for SUT or the number of a Env Node
        self.origin = origin
        # either 0 for SUT or the number of a Env Node
        self.target = target
        # timestamp
        self.ts = ts

        if self.origin in [0, '-']:
            self.type = "SUT"
        else:
            self.type = "Env"

    # required for debugging printing
    def __str__(self):
        return "signal={0}, origin={1}, target={2}, timestamp={3}".format(str(self.signal), str(self.origin),
                                                                          str(self.target), str(self.ts))


# contains list of Event
class Log:
    def __init__(self):
        self.events = []

    # required for debugging printing
    def __str__(self):
        ret = ""
        for event in self.events:
            ret += str(event) + "\n"
        return ret


# TODO: Currently the format only fits for <10 Env Nodes -> Scalability
def read_logs(file):
    logs = []
    print(type(logs))
    log_file = open(file, "r")
    lines = [line.replace('\n', '').replace('<', '').replace('>', '') for line in log_file.readlines()]

    i = -1
    for index, line in enumerate(lines):
        # line initializing new event feed for a log (log: x)
        if line[0] == "l":
            logs.append(Log())
            i += 1
        else:
            wholesignal, ts = line.split(',')
            ts = int(ts)
            # timeout represented by wildcard '.'
            if wholesignal[:2] == 'To':
                signal = "---"
                origin = "-"
                target = int(wholesignal[2])
            else:
                # first 3 characters are Req or Ack
                signal = wholesignal[:3]
                origin = int(wholesignal[3])
                target = int(wholesignal[4])
            logs[i].events.append(Event(signal, origin, target, ts))

    log_file.close()
    return logs


# TODO: Keep this for now
# def read_log(log_string):
#     log_file = open(file, "r")
#     print("\n--- " + file + " ---")
#     lines = [line.replace('\n', '').replace('<', '').replace('>', '') for line in log_file.readlines()]
#     # print(lines)
#     log = Log()
#     for line in lines:
#         wholesignal, ts = line.split(',')
#         ts = int(ts)
#         # timeout represented by wildcard '.'
#         if wholesignal == '.':
#             signal = "---"
#             origin = "-"
#             target = "-"
#         else:
#             # first 3 characters are Req or Ack
#             signal = wholesignal[:3]
#             origin = int(wholesignal[3])
#             target = int(wholesignal[4])
#         # print(signal + " " + origin + " " + target + " " + str(ts))
#         log.events.append(Event(signal, origin, target, ts))
#     log_file.close()
#     return log


def new_x(node):
    return stepsize * num_locations(node)


def new_id(node):
    return "id" + str(num_locations(node))


# my_log = read_log_from_file("logs/log1.txt")
# print(my_log)

# --- BEGIN my_alg ---

# load the blank system generated by UPPAAL as a starting point
sys = u.NTA.from_xml(path='xml-files/blank_system.xml')
sys.templates[0].graph.remove_node(('Template', 'id0'))
blank_template = copy.deepcopy(sys.templates[0])
sys.templates.pop()

# creates new template for SUT
sut = new_template("SUT")
env = []

# store used Channel names of SUT
sut_channels = []
# store used Channel names in general of adding to declarations
channels = []

#
stepsize = 200  # stepsize for locations
last_locations = []  # last used locations
active_locations = []


def active_index(node):
    return len(active_locations[node - 1]) + 1


passive_locations = []


def passive_index(node):
    return len(passive_locations[node - 1]) + 1


def all_locations(node):
    return passive_locations[node - 1] + active_locations[node - 1]


def has_end_loc(node):
    temp = False
    for location in all_locations(node):
        if location.name.name == "END":
            temp = True
    return temp


def get_end_loc(node):
    for location in all_locations(node):
        if location.name.name == "END":
            return location


# adds transition to SUT (if new), adds to used channels, determines label for Env transition
def new_channel(ori, tar, value, suffix):
    # BLOCK for Env Channel
    label = u.Label(kind="synchronisation", pos=sync_label_pos(ori, tar),
                    value=value + suffix)
    print("Creating Channel: " + value + suffix)
    # BLOCK for adding transition to SUT, if new Channel
    if suffix == "?":
        inverse = value + "!"
    elif suffix == "!":
        inverse = value + "?"
    else:
        inverse = None
        print("WRONG SUFFIX FOR CHANNEL CREATION")
    if value == "Ack":
        print("SETTING END LOCATION")
        tar.name = "END"

    # store used channels to write them to UPPAAL global declarations
    if value not in channels:
        channels.append(value)

    # TODO: Proper positioning of self-edges and labels for SUT (maybe even dynamic readjusting)
    # old ones to fit in a circle -> make it scalable
    # use nails, put label between nails
    if inverse not in sut_channels:
        sut_channels.append(inverse)
        sut_label = u.Label(kind="synchronisation", pos=sync_label_pos(sut_loc, sut_loc),
                            value=inverse)
        trans = u.Transition(source=sut_loc.id, target=sut_loc.id, synchronisation=sut_label)
        sut.add_trans(trans)
        # @see arrange_sut_edges
    return label


def add_qual_trans(node, src, tar, guard, comments, **kwargs):
    """
    Adds a new transition

    :param template node: Template
    :param loc src: Source location
    :param loc tar: Target location
    :param int guard: Guard values
    :param [int, int] nails: Position tuple for a Nail
    :param str comments: Comments
    :param str sync: Synchronisation Channel Label
    :return: the transition
    :rtype: trans
    """

    guard_label = u.Label(kind="guard", pos=guard_label_pos(src, tar),
                          value="cl>=" + str(guard))
    # standard assignment
    assignment_label = u.Label(kind="assignment",
                               pos=asgn_label_pos(src, tar), value="cl=0")
    comment = u.Label(kind="comments", pos=asgn_label_pos(src, tar),
                      value=comments)
    trans = u.Transition(source=src.id, target=tar.id, guard=guard_label,
                         assignment=assignment_label, comments=comment)
    # print("[" + templ.name.name + "] Adding transition from: " + src.name.name + " to: " + tar.name.name)
    # TODO: maybe add array of nails
    nails = kwargs.get('nails')
    if nails is not None:
        nail = u.Nail(pos=[nails[0], nails[1]])
        trans.nails = [nail]
    sync = kwargs.get('sync')
    if sync is not None:
        # redirect transition to end location as target
        # Assumption: After acknowledgment we are done with that Node
        if sync.value[0:3] == "Ack":
            if has_end_loc(node) and tar != get_end_loc(node):
                env[node - 1].del_loc(trans.target)
                trans.target = get_end_loc(node).id
            else:
                target = get_loc_by_id(all_locations(node), tar.id)
                print("SETTING END LOCATION")
                target.name.name = "END"
        trans.synchronisation = sync
    env[node - 1].add_trans(trans)
    return trans


def interval_extension(lb, ub, r):
    delta = r - (ub - lb)
    # TODO: Check whether this is valid
    # This ensures we only EXTEND the interval
    if delta > 0:
        new_lb = lb - delta
        new_ub = ub + delta
        return new_lb, new_ub
    else:
        return lb, ub


def get_loc_by_id(loc_list, id):
    for loc in loc_list:
        if loc.id == id:
            return loc
    return "Error while looking for id: " + id


# checks whether a location is in the targets of a list of transitions
def in_target_locs(loc, transitions):
    # print("\nlocation: " + loc.id)
    for trans in transitions:
        if trans.target == loc.id:
            # print("\ntarget: " + trans.target)
            return True
    return False


# this is how we add locations
sut_loc = sut.add_loc(u.Location(id="id0", pos=[0, 0]))

logs = read_logs("traces_output.txt")
# for log in logs:
#     print(log)
# iterate over the files in logs folder
for count, log in enumerate(logs):
    print("\nLog: " + str(count))
    # log = read_log("logs/" + filename)

    # TODO: This assumption is fine for now, Iam assuming it
    # count the Env Nodes, it has to be the same for all logs
    number_env_nodes = 0
    for event in log.events:
        # ignore timeouts
        if event.signal != "---":
            if event.origin > number_env_nodes:
                number_env_nodes = event.origin
            if event.target > number_env_nodes:
                number_env_nodes = event.target
    # print("Number of Nodes: " + str(number_env_nodes) + "\n")
    # create new template for Env Node, if we have none yet
    if not env:
        for i in range(1, number_env_nodes + 1):
            env.append(new_template("Node" + str(i)))

    # create clock declaration for every Env Template
    for node in env:
        node.declaration = u.Declaration("clock cl;")

    """ --- BEGIN INITIALIZATIONS --- """

    # initialize internal clocks and interval abstraction parameter
    internal_clock = []

    for i in range(1, number_env_nodes + 1):
        internal_clock.append(0)
    # initially 4
    R = 20
    # other initializations

    timeout_ts = []
    timeout_units = 0

    # returns the number of locations for a specific node
    def num_locations(node):
        return len(active_locations[node - 1]) + len(passive_locations[node - 1])


    def new_loc_name(loc_type, index):
        name = "L" + loc_type + str(index)
        print("New loc name: " + name)
        return name


    working_loc = []
    for i in range(number_env_nodes):
        active_locations.append([])
        passive_locations.append([])
        last_locations.append([])
        timeout_ts.append(0)
        working_loc.append(u.Location(id="id1337", pos=[0, 0], name=u.Name("1337", pos=[0, 0])))  # random init

    if count > 0:
        for i in range(number_env_nodes):
            working_loc[i] = get_loc_by_id(all_locations(i + 1), env[i].graph.initial_location[1])

    """ --- END INITIALIZATIONS --- """

    # iterate over all events in a log
    for event_index, event in enumerate(log.events):
        # Env event
        if event.type == "Env":
            signal = event.signal + str(event.origin) + str(event.target)
            print("Env Event: " + signal)
            proc = event.origin
            clock = event.ts - internal_clock[proc - 1]
            internal_clock[proc - 1] = event.ts

            # last event was timeout, we have to go to initial loc by assumption
            if timeout_ts[proc - 1] != 0:
                clock = internal_clock[proc - 1] - timeout_ts[proc - 1]
                print("timeout handling")
                init_loc = get_loc_by_id(all_locations(proc), env[proc - 1].graph.initial_location[1])
                if not hasattr(working_loc[proc - 1].invariant, 'value'):
                    # We have to create invariant for this location
                    working_loc[proc - 1].invariant = u.Label(kind="invariant", pos=[last_loc.pos[0], 20],
                                                              value="cl<=" + str(clock))
                    inv_ub = 0
                working_loc[proc - 1].invariant.value = "cl<=" + str(max(timeout_units, inv_ub))
                # appending the last location before the timeout
                last_locations[proc - 1].append(last_locations[proc - 1][-2])
                if not in_target_locs(init_loc, env[proc - 1].get_trans_by_source(working_loc[proc - 1])):
                    print("Repositioning location...")
                    add_qual_trans(node=proc, src=working_loc[proc - 1], tar=init_loc, guard=timeout_units,
                                   comments="timeout")  # nails=[-30, -30],
                    # reposition last location
                    repos_loc(working_loc[proc - 1], init_loc.pos[0], init_loc.pos[1] + stepsize)
                working_loc[proc - 1] = init_loc
                timeout_ts[proc - 1] = 0

            # Check the condition for Case 1
            cond = False
            # going through all transitions with source being the location we are currently in
            # TODO: Check whether this is fine, as it is different to paper
            print("Working loc is: " + working_loc[proc - 1].name.name)
            for transition in env[proc - 1].get_trans_by_source(working_loc[proc - 1]):
                # source_loc = get_loc_by_id(active_locations[proc-1], transition.source)
                source_loc = working_loc[proc - 1]
                # if source_loc is last_locations[proc-1][-1]:
                # TODO: Maybe dont use int here
                guard_lb = int(transition.guard.value[4:])
                target_loc = get_loc_by_id(passive_locations[proc - 1], transition.target)
                if hasattr(source_loc.invariant, 'value'):
                    inv_ub = int(source_loc.invariant.value[4:])
                else:
                    inv_ub = guard_lb
                lb, ub = interval_extension(guard_lb, inv_ub, R)
                if hasattr(transition.synchronisation, 'value'):
                    if signal + "!" == transition.synchronisation.value and lb <= clock <= ub:
                        cond = True
                        found_trans = transition
                        break

            # Case 1
            if cond:
                print("Env Case 1 for " + str(env[proc - 1].name.name))
                # update corresponding guard
                found_trans.guard.value = "cl>=" + str(min(clock, guard_lb))
                # update corresponding invariant
                if hasattr(source_loc.invariant, 'value'):
                    source_loc.invariant.value = "cl<=" + str(max(clock, inv_ub))
                else:
                    position = [source_loc.pos[0], source_loc.pos[1]]
                    source_loc.invariant = u.Label(kind="invariant",
                                                   pos=inv_loc_pos(position[0], position[1]),
                                                   value="cl<=" + str(max(clock, inv_ub)))

                working_loc[proc - 1] = target_loc

            # Case 2
            else:
                print("Env Case 2 for " + str(env[proc - 1].name.name))
                if active_index(proc) > 1:  # If not first active location
                    # working_active_loc = working_loc[proc-1]
                    working_active_loc = active_locations[proc - 1][-1]  # This considers the top of the stack
                else:  # If first active location
                    # add location to the active locations
                    position = [new_x(proc), 0]
                    new_active = u.Location(id=new_id(proc), pos=position,
                                            name=u.Name(new_loc_name(loc_type="a", index=active_index(proc)),
                                                        pos=name_loc_pos(position[0], position[1])),
                                            invariant=u.Label(kind="invariant",
                                                              pos=inv_loc_pos(position[0], position[1]),
                                                              value="cl<=" + str(clock)))
                    active_locations[proc - 1].append(env[proc - 1].add_loc(new_active))
                    last_locations[proc - 1].append(new_active)
                    working_active_loc = new_active

                if has_end_loc(proc):
                    end_loc = get_end_loc(proc)
                    if not in_target_locs(end_loc, env[proc - 1].get_trans_by_source(working_active_loc)):
                        add_qual_trans(node=proc, src=working_active_loc, tar=end_loc, guard=clock,
                                       comments="controllable",
                                       sync=new_channel(working_active_loc, end_loc, signal, "!"))
                        working_active_loc.invariant = u.Label(kind="invariant", pos=inv_loc_pos(working_active_loc.pos[0],
                                                                                                 working_active_loc.pos[1]),
                                                               value="cl<=" + str(clock))
                    working_loc[proc - 1] = end_loc
                else:
                    # add location to the passive locations
                    position = [new_x(proc), 0]
                    new_passive = u.Location(id=new_id(proc), pos=position,
                                             name=u.Name(new_loc_name(loc_type="p", index=passive_index(proc)),
                                                         pos=name_loc_pos(position[0], position[1])))
                    passive_locations[proc - 1].append(env[proc - 1].add_loc(new_passive))
                    last_locations[proc - 1].append(new_passive)
                    working_loc[proc - 1] = new_passive
                    # add transition
                    add_qual_trans(node=proc, src=working_active_loc, tar=new_passive, guard=clock,
                                   comments="controllable",
                                   sync=new_channel(working_active_loc, new_passive, signal, "!"))
        # SUT Event
        else:
            print("SUT Event: " + event.signal + str(event.origin) + str(event.target))
            signal = event.signal + str(event.origin) + str(event.target)
            proc = event.target
            if event.origin == "-":
                print("timeout event, skipping...")
                timeout_ts[proc - 1] = event.ts
                # accessing predecessor
                timeout_units = timeout_ts[proc - 1] - log.events[event_index - 1].ts
                continue
            clock = event.ts - internal_clock[proc - 1]
            internal_clock[proc - 1] = event.ts
            last_loc = working_loc[proc - 1]
            print("Working loc is: " + working_loc[proc - 1].name.name)

            """ --- BEGIN TIMEOUT HANDLING --- """
            # last event was timeout
            if timeout_ts[proc - 1] != 0:
                clock = internal_clock[proc - 1] - timeout_ts[proc - 1]
                print("timeout handling")
                last_loc = working_loc[proc - 1]
                cond = False
                for transition in env[proc - 1].get_trans_by_source(last_loc):
                    # we dont go back to initial location by assumption
                    if transition.target != init_loc.id:
                        guard_lb = int(transition.guard.value[4:])
                        target_loc = get_loc_by_id(all_locations(proc), transition.target)
                        inv_ub = int(last_loc.invariant.value[4:])
                        lb, ub = interval_extension(guard_lb, inv_ub, R)
                        print("lb: " + str(lb) + ", clock: " + str(clock) + ", ub: " + str(ub))
                        # # need this
                        # if not hasattr(transition, 'synchronisation'):
                        #     compare = signal + "?"
                        # else:
                        #     compare = transition.synchronisation.value
                        if lb <= clock <= ub:
                            cond = True
                            found_trans = transition
                            break
                if cond:
                    # update corresponding guard
                    found_trans.guard.value = "cl>=" + str(min(clock, guard_lb))
                    # update corresponding invariant
                    last_loc.invariant.value = "cl<=" + str(max(clock, inv_ub))
                    working_loc[proc - 1] = target_loc
                else:
                    # create new active/timeout location
                    position = [working_loc[proc - 1].pos[0] + stepsize, working_loc[proc - 1].pos[1]]
                    new_active = u.Location(id=new_id(proc), pos=position,
                                            name=u.Name(new_loc_name(loc_type="a", index=active_index(proc)),
                                                        pos=name_loc_pos(position[0], position[1])))
                    active_locations[proc - 1].append(env[proc - 1].add_loc(new_active))
                    last_locations[proc - 1].append(new_active)
                    if not hasattr(last_loc.invariant, 'value'):
                        # We have to create invariant for this location
                        last_loc.invariant = u.Label(kind="invariant",
                                                     pos=inv_loc_pos(last_loc.pos[0], last_loc.pos[1]),
                                                     value="cl<=" + str(clock))
                        inv_ub = 0
                    last_loc.invariant.value = "cl<=" + str(max(timeout_units, inv_ub))

                    add_qual_trans(node=proc, src=last_loc, tar=new_active, guard=timeout_units,
                                   comments="timeout")  # nails=[-30, -30],

                    # create new active location
                    position = [working_loc[proc - 1].pos[0] + 2 * stepsize, working_loc[proc - 1].pos[1]]
                    new_active2 = u.Location(id=new_id(proc), pos=position,
                                             name=u.Name(new_loc_name(loc_type="a", index=active_index(proc)),
                                                         pos=name_loc_pos(position[0], position[1])))
                    active_locations[proc - 1].append(env[proc - 1].add_loc(new_active2))
                    last_locations[proc - 1].append(new_active2)
                    if not hasattr(new_active.invariant, 'value'):
                        # We have to create invariant for this location
                        new_active.invariant = u.Label(kind="invariant",
                                                       pos=inv_loc_pos(new_active.pos[0], new_active.pos[1]),
                                                       value="cl<=" + str(clock))
                        inv_ub = 0
                    new_active.invariant.value = "cl<=" + str(max(clock, inv_ub))

                    add_qual_trans(node=proc, src=new_active, tar=new_active2, guard=clock,
                                   comments="observable",
                                   sync=new_channel(new_active, new_active2, signal, "?"))  # nails=[-30, -30],

                    working_loc[proc - 1] = new_active2
                timeout_ts[proc - 1] = 0
                continue

            """ --- END TIMEOUT HANDLING --- """

            # Check the condition for Case 1
            cond = False
            for transition in env[proc - 1].get_trans_by_source(working_loc[proc - 1]):
                # TODO: Maybe dont use int here
                guard_lb = int(transition.guard.value[4:])
                source_loc = source_loc = working_loc[proc - 1]
                target_loc = get_loc_by_id(all_locations(proc), transition.target)
                if hasattr(source_loc, 'invariant'):
                    inv_ub = int(source_loc.invariant.value[4:])
                else:
                    inv_ub = clock
                lb, ub = interval_extension(guard_lb, inv_ub, R)
                if hasattr(transition.synchronisation, 'value'):
                    print("SIGNAL: " + signal + "?, SYNC VAL: " + transition.synchronisation.value)
                    print("lb: " + str(lb) + ", clock: " + str(clock) + ", ub: " + str(ub))
                    if signal + "?" == transition.synchronisation.value and lb <= clock <= ub:
                        cond = True
                        found_trans = transition
                        break
                # else:
                #     if lb <= clock <= ub:
                #         cond = True
                #         found_trans = transition
                #         break
                # print("-----------------------------------------------------\n")
                # print(transition.target)

            # Case 1
            if cond:
                print("SUT Case 1 for " + str(env[proc - 1].name.name))
                # update corresponding guard
                found_trans.guard.value = "cl>=" + str(min(clock, guard_lb))
                # update corresponding invariant
                if not hasattr(source_loc, 'invariant'):
                    source_loc.invariant = u.Label(kind="invariant",
                                                   pos=inv_loc_pos(source_loc.pos[0], source_loc.pos[1]))
                source_loc.invariant.value = "cl<=" + str(max(clock, inv_ub))
                working_loc[proc - 1] = target_loc

            # Case 2
            else:
                print("SUT Case 2 for " + str(env[proc - 1].name.name))
                if hasattr(last_loc.invariant, 'value'):
                    inv_ub = int(last_loc.invariant.value[4:])
                else:
                    # We have to create invariant for this location first
                    last_loc.invariant = u.Label(kind="invariant", pos=inv_loc_pos(last_loc.pos[0], last_loc.pos[1]),
                                                 value="cl<=" + str(clock))
                    inv_ub = clock

                last_loc.invariant.value = "cl<=" + str(max(clock, inv_ub))
                # add location to the active locations
                position = [new_x(proc), 0]
                new_active = u.Location(id=new_id(proc), pos=position,
                                        name=u.Name(new_loc_name(loc_type="a", index=active_index(proc)),
                                                    pos=name_loc_pos(position[0], position[1])))
                active_locations[proc - 1].append(env[proc - 1].add_loc(new_active))

                last_locations[proc - 1].append(new_active)
                working_active_loc = new_active
                working_loc[proc - 1] = new_active
                # add transition
                add_qual_trans(node=proc, src=last_loc, tar=working_active_loc, guard=clock,
                               comments="observable", sync=new_channel(last_loc, working_active_loc, signal, "?"))

# --- Finishing Ops ---

# testwise addition of locations
# for node in env:
#     node.add_loc(u.Location(id="id0", pos=[0, 0], name="La1"))
#     node.add_loc(u.Location(id="id1", pos=[200, 200]))

# write declarations
declarations = "// Place global declarations here.\n"
if channels:
    declarations += "chan "
    for i, channel in enumerate(channels):
        if i == 0:
            declarations += channel
        else:
            declarations += ", " + channel
    declarations += ";"
sys.declaration = u.Declaration(declarations)

# instantiate the templates as processes
template_instantiations = "// Place template instantiations here.\n"
template_instantiations += "NODE0 = " + sut.name.name + "();\n"
for i, template in enumerate(env):
    template_instantiations += "NODE" + str(i + 1) + " = " + template.name.name + "();\n"

# add processes to system
system_processes = "// List one or more processes to be composed into a system.\nsystem "
system_processes += sut.name.name
for i, template in enumerate(env):
    system_processes += ", " + template.name.name
system_processes += ";"

# write system declarations
system_declarations = template_instantiations + system_processes
sys.system = u.SystemDeclaration(system_declarations)

# save the system to xml
sys.to_file(path='xml-files/output.xml', pretty=True)

# run UPPAAL and suppressing it's output
running_uppaal = subprocess.call(['java', '-jar', 'UPPAAL/uppaal.jar', 'xml-files/output.xml'],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.STDOUT)
