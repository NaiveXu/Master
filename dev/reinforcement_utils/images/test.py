import torch
from torch.autograd import Variable
import torch.nn.functional as F
import random
import matplotlib.pyplot as plt
import numpy as np
import math


GAMMA = 0.5
def validate(model, epoch, optimizer, test_loader, args, reinforcement_learner, episode, criterion,  multi_state=False, state_size=5, batch_size=32):

    # Initialize training:
    model.eval()

    # Collect a random batch:
    image_batch, label_batch = test_loader.__iter__().__next__()

    # Episode Statistics:
    episode_correct = 0.0
    episode_predict = 0.0
    episode_request = 0.0
    episode_reward = 0.0

    # Create initial state:
    if (multi_state):
        state = []
        label_dict = []
        for i in range(batch_size):
            state.append([0 for i in range(state_size*state_size)])
            label_dict.append({})
    else:
        state = []
        label_dict = []
        for i in range(batch_size):
            state.append([0 for i in range(args.class_vector_size)])
            label_dict.append({})

    # Initialize model between each episode:
    hidden = model.reset_hidden(batch_size)

    # Statistics again:    
    request_dict = {1: [], 2: [], 5: [], 10: []}
    accuracy_dict = {1: [], 2: [], 5: [], 10: []}
    prediction_accuracy_dict = {1: [], 2: [], 5: [], 10: []}

    if (multi_state):
        class_representations = get_multiclass_representations(batch_size, args.class_vector_size)

    # EPISODE LOOP:
    for i_e in range(len(label_batch)):
        episode_labels = label_batch[i_e]
        episode_images = image_batch[i_e]

        if (not multi_state):
            class_representations = get_singleclass_representations(batch_size, args.class_vector_size, episode_labels)

        # Tensoring the state:
        state = torch.FloatTensor(state)
        
        # Need to add image to the state vector:
        flat_images = episode_images.squeeze().view(batch_size, -1)

        # Concatenating possible labels/zero vector with image, to create the environment state:
        if (multi_state):
            state = state.view(batch_size, -1)
            state = torch.cat((state, flat_images), 1)
        else:
            state = torch.cat((state, flat_images), 1)

        
        for i in range(batch_size):
            true_label = episode_labels[i].item()

            # Logging statistics:
            if (true_label not in label_dict[i]):
                label_dict[i][true_label] = 1
            else:
                label_dict[i][true_label] += 1

        # Selecting an action to perform (Epsilon Greedy):
        if (args.cuda):
            q_values, hidden = model(Variable(state, volatile=True).type(torch.FloatTensor).cuda(), hidden)
        else:
            q_values, hidden = model(Variable(state, volatile=True).type(torch.FloatTensor), hidden)

        # Choosing the largest Q-values:
        model_actions = q_values.data.max(1)[1].view(batch_size)

        # NOT Performing Epsilon Greedy Exploration:
        agent_actions = model_actions
        
        # Collect rewards:
        # Collect rewards:
        if (multi_state):
            rewards = reinforcement_learner.collect_reward_multistate_batch(agent_actions, class_representations, batch_size, episode_labels)
        else:
            rewards = reinforcement_learner.collect_reward_batch(agent_actions, class_representations, batch_size)

        # Collecting average reward at time t:
        episode_reward += float(sum(rewards)/batch_size)

        # Just some statistics logging:
        stats = update_dicts(batch_size, episode_labels, rewards, reinforcement_learner, label_dict, request_dict, accuracy_dict, prediction_accuracy_dict)
        episode_predict += stats[0]
        episode_correct += stats[1]
        episode_request += stats[2]

        # Observe next state and images:
        if (multi_state):
            next_state_start = reinforcement_learner.next_multistate_batch(agent_actions, class_representations, batch_size, episode_labels)
        else:
            next_state_start = reinforcement_learner.next_state_batch(agent_actions, class_representations, batch_size)
        
        # Update current state:
        state = next_state_start

        ### END TRAIN LOOP ###

    for key in request_dict.keys():
        request_dict[key] = float(sum(request_dict[key])/len(request_dict[key]))
        accuracy_dict[key] = float(sum(accuracy_dict[key])/len(accuracy_dict[key]))
        prediction_accuracy_dict[key] = float(sum(prediction_accuracy_dict[key])/max(1, len(prediction_accuracy_dict[key])))

    print("\n---Validation Statistics---\n")

    print("\n--- Epoch " + str(epoch) + ", Episode " + str(episode + i + 1) + " Statistics ---")
    print("Instance\tAccuracy\tRequests")       
    for key in accuracy_dict.keys():
        accuracy = accuracy_dict[key]
        request_percentage = request_dict[key]    
        
        print("Instance " + str(key) + ":\t" + str(100.0*accuracy)[0:4] + " %" + "\t\t" + str(100.0*request_percentage)[0:4] + " %")
    

    # Even more status update:
    print("\n+------------------STATISTICS----------------------+")
    total_prediction_accuracy = float((100.0 * episode_correct) / max(1, episode_predict-episode_request))
    print("Batch Average Prediction Accuracy = " + str(total_prediction_accuracy)[:5] +  " %")
    total_accuracy = float((100.0 * episode_correct) / episode_predict)
    print("Batch Average Accuracy = " + str(total_accuracy)[:5] +  " %")
    total_requests = float((100.0 * episode_request) / (batch_size*args.episode_size))
    print("Batch Average Requests = " + str(total_requests)[:5] + " %")
    total_reward = float(episode_reward)
    print("Batch Average Reward = " + str(total_reward)[:5])
    print("+--------------------------------------------------+\n")

    return [total_prediction_accuracy, total_requests, total_reward, total_accuracy], request_dict, accuracy_dict, prediction_accuracy_dict


def get_multiclass_representations(batch_size, classes):
    label_list = ['a', 'b', 'c', 'd', 'e']
    bits = np.array([np.array([np.array(np.random.choice(len(label_list), len(label_list), replace=True)) for c in range(classes)]) for b in range(batch_size)])
    one_hot_vectors = np.array([np.array([np.zeros((len(label_list), len(label_list))) for c in range(classes)]) for b in range(batch_size)])
    for b in range(batch_size):
        for c in range(classes):
            one_hot_vectors[b][c][np.arange(len(label_list)), bits[b][c]] = 1
    return one_hot_vectors

def get_singleclass_representations(batch_size, classes, episode_labels):
    one_hot_labels = []
    for b in range(batch_size):
        true_label = episode_labels.squeeze()[b]
        one_hot_labels.append([1 if j == true_label else 0 for j in range(classes)])

    return one_hot_labels


def update_dicts(batch_size, episode_labels, rewards, reinforcement_learner, label_dict, request_dict, accuracy_dict, prediction_accuracy_dict):
    predict = 0.0
    request = 0.0
    correct = 0.0
    for i in range(batch_size):
        true_label = episode_labels[i].item()

        # Statistics:
        reward = rewards[i]
        if (reward == reinforcement_learner.request_reward):
            request += 1.0
            predict += 1.0
            if (label_dict[i][true_label] in request_dict):
                request_dict[label_dict[i][true_label]].append(1)
            if (label_dict[i][true_label] in accuracy_dict):
                accuracy_dict[label_dict[i][true_label]].append(0)
        elif (reward == reinforcement_learner.prediction_reward):
            correct += 1.0
            predict += 1.0
            if (label_dict[i][true_label] in request_dict):
                request_dict[label_dict[i][true_label]].append(0)
            if (label_dict[i][true_label] in accuracy_dict):
                accuracy_dict[label_dict[i][true_label]].append(1)
                prediction_accuracy_dict[label_dict[i][true_label]].append(1)
        else:
            predict += 1.0
            if (label_dict[i][true_label] in request_dict):
                request_dict[label_dict[i][true_label]].append(0)
            if (label_dict[i][true_label] in accuracy_dict):
                accuracy_dict[label_dict[i][true_label]].append(0)
                prediction_accuracy_dict[label_dict[i][true_label]].append(0)

    return predict, correct, request

