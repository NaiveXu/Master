import torch
from torch.autograd import Variable
import random
from transition import Transition

# Discount factor for future rewards, and Greedy Epsilon Constant:
GAMMA = 0.5
EPS = 0.05


def train(model, epoch, optimizer, train_loader, args, writer, reinforcement_learner, request_dict, accuracy_dict, episode):

    # Initialize training:
    model.train()

    batch_correct = 0.0
    batch_predict = 0.0
    batch_request = 0.0
    batch_reward = 0.0

    for b in range(args.batch_size):
        
        # Collect a random batch:
        image_batch, label_batch = train_loader.__iter__().__next__()

        # Keep a memory of the episode:
        transitions = []

        # Episode Statistics:
        episode_correct = 0.0
        episode_predict = 0.0
        episode_request = 0.0
        episode_reward = 0.0

        # Create initial state:
        state = []
        label_dict = []
        for i in range(args.mini_batch_size):
            state.append([0 for i in range(args.class_vector_size)])
            label_dict.append({})

        # Initialize model between each episode:
        hidden = model.reset_hidden(args.mini_batch_size)

        # Statistics again:    
        for v in request_dict.values():
            v.append([])
        for v in accuracy_dict.values():
            v.append([])

        # Placeholder for loss Variable:
        if (args.cuda):
            loss = Variable(torch.zeros(args.mini_batch_size).type(torch.Tensor)).cuda()
        else:
            loss = Variable(torch.zeros(args.mini_batch_size).type(torch.Tensor))

        # EPISODE LOOP:
        for i_e in range(len(label_batch)):

            # Zeroing accumulated gradients:
            optimizer.zero_grad()

            episode_labels = label_batch[i_e]
            episode_images = image_batch[i_e]

            # Tensoring the state:
            state = torch.FloatTensor(state)
            
            # Need to add image to the state vector:
            flat_images = episode_images.squeeze().view(args.mini_batch_size, -1)

            # Concatenating possible labels/zero vector with image, to create the environment state:
            state = torch.cat((state, flat_images), 1)
            
            one_hot_labels = []
            for i in range(args.mini_batch_size):
                true_label = episode_labels[i]

                # Creating one hot labels:
                one_hot_labels.append([1 if j == true_label else 0 for j in range(args.class_vector_size)])

                # Logging statistics:
                if (true_label not in label_dict[i]):
                    label_dict[i][true_label] = 1
                else:
                    label_dict[i][true_label] += 1

            # Selecting an action to perform (Epsilon Greedy):
            if (args.cuda):
                q_values, hidden = model(Variable(state).type(torch.FloatTensor).cuda(), hidden)
            else:
                q_values, hidden = model(Variable(state).type(torch.FloatTensor), hidden)

            # Choosing the largest Q-values:
            model_actions = q_values.data.max(1)[1].view(args.mini_batch_size)

            # Performing Epsilon Greedy Exploration:
            agent_actions = []
            for i in range(args.mini_batch_size):

                # Model choice:
                if (random.random() > EPS):
                    agent_actions.append(model_actions[i])

                # Epsilong Greedy:
                else:
                    epsilon_action = random.randint(0, 2)

                    # Request:
                    if (epsilon_action == 0):
                        agent_actions.append(args.class_vector_size)

                    # Incorrect Prediction:
                    elif (epsilon_action == 1):
                        wrong_label = random.randint(0, args.class_vector_size - 1)
                        while (wrong_label == episode_labels[i]):
                            wrong_label = random.randint(0, args.class_vector_size - 1)
                        agent_actions.append(wrong_label)

                    # Correct Prediction:
                    else:
                        agent_actions.append(episode_labels[i])
            
            # Collect rewards:
            rewards = reinforcement_learner.collect_reward_batch(agent_actions, one_hot_labels, args.mini_batch_size)

            # Collecting average reward at time t:
            episode_reward += float(sum(rewards)/args.mini_batch_size)

            # Just some statistics logging:
            for i in range(args.mini_batch_size):
                true_label = episode_labels[i]

                # Statistics:
                reward = rewards[i]
                if (reward == reinforcement_learner.request_reward):
                    episode_request += 1
                    episode_predict += 1
                    if (label_dict[i][true_label] in request_dict):
                        request_dict[label_dict[i][true_label]][-1].append(1)
                    if (label_dict[i][true_label] in accuracy_dict):
                        accuracy_dict[label_dict[i][true_label]][-1].append(0)
                elif (reward == reinforcement_learner.prediction_reward):
                    episode_correct += 1.0
                    episode_predict += 1.0
                    if (label_dict[i][true_label] in request_dict):
                        request_dict[label_dict[i][true_label]][-1].append(0)
                    if (label_dict[i][true_label] in accuracy_dict):
                        accuracy_dict[label_dict[i][true_label]][-1].append(1)
                else:
                    episode_predict += 1.0
                    if (label_dict[i][true_label] in request_dict):
                        request_dict[label_dict[i][true_label]][-1].append(0)
                    if (label_dict[i][true_label] in accuracy_dict):
                        accuracy_dict[label_dict[i][true_label]][-1].append(0)

            # Tensoring the reward:
            #rewards = Variable(torch.Tensor([rewards]))
            rewards = torch.Tensor([rewards])

            # Observe next state and images:
            next_state_start = reinforcement_learner.next_state_batch(agent_actions, one_hot_labels, args.mini_batch_size)

            # Need to collect the representative Q-values:
            agent_actions = torch.LongTensor(agent_actions).unsqueeze(1)
            #agent_actions = Variable(torch.LongTensor(agent_actions).unsqueeze(1))
            #current_q_values = q_values.gather(1, agent_actions)

            # Non-final state:
            if (i_e < args.episode_size - 1):
                # Collect next image:
                next_flat_images = image_batch[i_e + 1].squeeze().view(args.mini_batch_size, -1)

                # Create next state:
                next_state = torch.cat((torch.FloatTensor(next_state_start), next_flat_images), 1)

                transitions.append(Transition(state, agent_actions, next_state, rewards))
                """
                # Get target value for next state:
                target_value = model(Variable(next_state, volatile=True), hidden)[0].max(1)[0]

                # Making it un-volatile again:
                target_value.volatile = False

                # Discounting the next state + reward collected in this state:
                discounted_target_value = (GAMMA*target_value) + rewards

                # Calculating Bellman error:
                difference = discounted_target_value.squeeze().sub(current_q_values)
                loss = loss.add(difference.pow(2).squeeze())
                """

            # Final state:
            else:
                transitions.append(Transition(state, agent_actions, None, rewards))
                """
                # As there is no next state, we only have the rewards:
                discounted_target_value = rewards


                # Calculating Bellman error:
                difference = discounted_target_value.squeeze().sub(current_q_values)
                loss = loss.add(difference.pow(2).squeeze())
                """
            
            # Update current state:
            state = next_state_start

            ### END TRAIN LOOP ###

        optimize(transitions, model, args)

        """
        # Zeroing accumulated gradients:
        optimizer.zero_grad()

        # Averaging Loss over batch (SGD):
        avg_loss = torch.mean(loss)

        # Backpropagating error:
        avg_loss.backward()

        # Taking one step in the SGD optimizer:
        optimizer.step()
        """


        # Collect stats:
        batch_correct += episode_correct
        batch_predict += episode_predict
        batch_request += episode_request
        batch_reward += episode_reward

    

    print("\n--- Epoch " + str(epoch) + ", Episode " + str(episode + b + 1) + " Statistics ---")
    print("Instance\tAccuracy\tRequests")       
    for key in accuracy_dict.keys():
        prediction_batch = accuracy_dict[key][(-1*args.batch_size):]
        request_batch = request_dict[key][(-1*args.batch_size):]
        
        # Accuracy:
        predictions = .0
        nof_predictions = .0

        # Request:
        requests = .0
        nof_requests = .0

        # Averaging:
        for episode in range(len(prediction_batch)):

            # Accuracy:
            predictions += sum(prediction_batch[episode])
            nof_predictions += len(prediction_batch[episode])

            # Request:
            requests += sum(request_batch[episode])
            nof_requests += len(request_batch[episode])

        accuracy = float(predictions/nof_predictions)
        request_percentage = float(requests/nof_requests)
        
        print("Instance " + str(key) + ":\t" + str(100.0*accuracy)[0:4] + " %" + "\t\t" + str(100.0*request_percentage)[0:4] + " %")
    

    # Even more status update:
    print("\n+------------------STATISTICS----------------------+")
    total_prediction_accuracy = float((100.0 * batch_correct) / max(1, batch_predict-batch_request))
    print("Batch Average Prediction Accuracy = " + str(total_prediction_accuracy)[:5] +  " %")
    total_accuracy = float((100.0 * batch_correct) / batch_predict)
    print("Batch Average Accuracy = " + str(total_accuracy)[:5] +  " %")
    total_loss = float(avg_loss.data[0])
    print("Batch Average Loss = " + str(total_loss)[:5])
    total_requests = float((100.0 * batch_request) / (args.batch_size*args.episode_size))
    print("Batch Average Requests = " + str(total_requests)[:5] + " %")
    total_reward = float(batch_reward/args.batch_size)
    print("Batch Average Reward = " + str(total_reward)[:5])
    print("+--------------------------------------------------+\n")

    ### LOGGING TO TENSORBOARD ###
    data = {
        'training_total_requests': total_requests,
        'training_total_accuracy': total_accuracy,
        'training_total_loss': total_loss,
        'training_average_reward': total_reward
    }

    for tag, value in data.items():
        writer.scalar_summary(tag, value, epoch)
    ### DONE LOGGING ###

    return total_prediction_accuracy, total_requests, total_accuracy, total_loss, total_reward, request_dict, accuracy_dict


def optimize(transitions, model, args):

    batch = Transition(*zip(*transitions))

    hidden = model.reset_hidden(args.mini_batch_size)

    non_final_mask = torch.ByteTensor(tuple(map(lambda s: s is not None,
                                          batch.next_state)))
    non_final_next_states = Variable(torch.cat([s for s in batch.next_state
                                                if s is not None]),
                                     volatile=True)

    state_batch = Variable(torch.cat(batch.state))
    action_batch = Variable(torch.cat(batch.action))
    reward_batch = Variable(torch.cat(batch.reward))

    q_values, hidden = model(state_batch, hidden, seq=args.episode_size)

    print(q_values)
    print(action_batch)
    state_action_values = q_values.gather(1, action_batch)

    # Compute V(s_{t+1}) for all next states.
    next_state_values, _ = Variable(torch.zeros(args.episode_size).type(Tensor), hidden)
    next_state_values[non_final_mask] = model(non_final_next_states, hidden, seq=args.episode_size).max(1)[0]
    # Now, we don't want to mess up the loss with a volatile flag, so let's
    # clear it. After this, we'll just end up with a Variable that has
    # requires_grad=False
    next_state_values.volatile = False
    # Compute the expected Q values
    expected_state_action_values = (next_state_values * GAMMA) + reward_batch

    # Compute Huber loss
    loss = F.smooth_l1_loss(state_action_values, expected_state_action_values)

    # Optimize the model
    optimizer.zero_grad()
    loss.backward()

    for param in model.parameters():
        param.grad.data.clamp_(-1, 1)
    optimizer.step()





def print_graph(grad_fn):
    seen = set()
    params = None

    def size_to_str(size):
        return '('+(', ').join(['%d' % v for v in size])+')'

    def add_nodes(var):

        
        if torch.is_tensor(var):
            print("Node Orange = IS TENSOR: ", str(id(var)))
        elif hasattr(var, 'variable'):
            u = var.variable
            name = param_map[id(u)] if params is not None else ''
            node_name = '%s\n %s' % (name, size_to_str(u.size()))
            print("Node BLUE = ", str(id(var)), node_name)
        else:
            print("Node = ", str(type(var).__name__), str(id(var)))
        if var not in seen:
            seen.add(var)
            if hasattr(var, 'next_functions'):
                for u in var.next_functions:
                    if u[0] is not None:
                        add_nodes(u[0])
            if hasattr(var, 'saved_tensors'):
                for t in var.saved_tensors:
                    add_nodes(t)
    add_nodes(grad_fn)

