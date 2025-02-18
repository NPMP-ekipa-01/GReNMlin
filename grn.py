
import numpy as np
import simulator
from helpers import powerset

import networkx as nx
import matplotlib.pyplot as plt



class GRN:
    def __init__(self):
        self.species = []        
        self.species_names = []
        self.input_species_names = []
        self.genes = []

    def add_input_species(self, name):        
        self.add_species(name, 0) # input species are species that do not degrade
        self.input_species_names.append(name)

    def add_species(self, name, delta):
        self.species.append({'name': name, 'delta': delta})
        self.species_names.append(name)

    """
        regulator = {'name': str - name,
                     'type': int - -1 / 1],
                     'Kd': Kd,
                     'n': n}
        product = {'name': str - name}

    """

    def add_gene(self, alpha, regulators, products, logic_type='mixed'):
        if logic_type == 'mixed':
            logic_type = np.random.choice(['and', 'or'])

        gene = {'alpha': alpha,
                'regulators': regulators,
                'products': products,
                'logic_type': logic_type}
        
        for regulator in regulators:
            if regulator['name'] not in self.species_names:
                print(f'{regulator["name"]} not in species!')

        for product in products:
            if product['name'] not in self.species_names:
                print(f'{product["name"]} not in species!')


        self.genes.append(gene)


    def generate_equations(self):
        equations = {}
        
        for species in self.species:
            equations[species['name']] = [f'-{species["name"]}*{species["delta"]}']

        for gene in self.genes:
            
            up = []
            down = []
            logic_type = gene['logic_type']


            for regulator in gene['regulators']:
                name = regulator['name']
                n = regulator['n']
                Kd = regulator['Kd']
                
        
                regulator_term = f'(({name}/{Kd})**{n})'
                
                if regulator['type'] == 1:
                    up.append(regulator_term)
                
                down.append(regulator_term)

            if not up:
                up = ['1']

            if logic_type == 'or':
                up = "+".join(powerset(up, op="*"))
            elif logic_type == 'and':
                up = '*'.join(up)
            elif logic_type == '':
                up = up[0]
            else:
                print("Invalid logic type!")
                return

            down = "+".join(['1'] + powerset(down, op="*"))

            terms = f'{gene["alpha"]}*({up})/({down})'

            for product in gene['products']:
                equations[product['name']].append(terms)

        return equations

    def generate_model(self, fname='model.py'):
        equations = self.generate_equations()

        with open(fname, 'w') as f: 
            print(f'import numpy as np \n', file = f)
            print(f'def solve_model(T,state):', file = f)
            
            all_keys = ', '.join([f'{key}' for key in equations.keys()])
            all_dkeys = ', '.join([f'd{key}' for key in equations.keys()])
            
            print(f'    {all_keys} = state', file=f)

            for key in equations.keys():
                print(f'    d{key} = {"+".join(equations[key])}', file=f)
                
            print(f'    return np.array([{all_dkeys}])', file=f)
            
            #print('',file=f)
            print('',file=f)
            print(f'def solve_model_steady(state):', file = f)
            print(f'    return solve_model(0, state)', file = f)


    def plot_network(self):
        activators = {s:[] for s in self.species_names}
        inhibitors = {s:[] for s in self.species_names}


        for gene in self.genes:
            for product in gene['products']:
                activators[product['name']].extend([x['name'] for x in gene['regulators'] if x['type'] == 1])
                inhibitors[product['name']].extend([x['name'] for x in gene['regulators'] if x['type'] == -1])

        edges_act = set()
        edges_inh = set()

        for prod in activators:
            for reg in activators[prod]:
                edges_act.add((reg, prod))        

        for prod in inhibitors:
            for reg in inhibitors[prod]:
                edges_inh.add((reg, prod))        

        edges_both = edges_act & edges_inh
        edges_act -= edges_both
        edges_inh -= edges_both

        edges = list(edges_both) + list(edges_act) + list(edges_inh)
        colors = ['orange']*len(edges_both) + ['blue']*len(edges_act) + ['red']*len(edges_inh)

        G = nx.DiGraph()
        G.add_edges_from(edges)
        nx.draw_networkx(G, pos=nx.circular_layout(G), arrows=True, node_color = 'w', edge_color=colors)
        plt.show()



if __name__ == "__main__":
    my_grn = GRN()
    my_grn.add_input_species("X1")
    my_grn.add_input_species("X2")

    my_grn.add_species("Y", 0.1)

    #print(my_grn.species)
    #print(my_grn.species_names)

    
    regulators = [{'name': 'X1', 'type': -1, 'Kd': 5, 'n': 2},
                  {'name': 'X2', 'type': 1, 'Kd': 5, 'n': 3}]
    products = [{'name': 'Y'}]
    my_grn.add_gene(10, regulators, products)

    regulators = [{'name': 'X1', 'type': 1, 'Kd': 5, 'n': 2},
                  {'name': 'X2', 'type': -1, 'Kd': 5, 'n': 3}]
    products = [{'name': 'Y'}]
    my_grn.add_gene(10, regulators, products)

    #print(my_grn.genes)

    IN = np.zeros(len(my_grn.input_species_names))
    IN[0]=100
    IN[1]=100

    simulator.simulate_single(my_grn, IN)








