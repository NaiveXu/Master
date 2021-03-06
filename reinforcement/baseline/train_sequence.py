import torch
from torch.autograd import Variable
from transition import Transition

def train(model, epoch, optimizer, train_loader, args, writer, accuracy_dict, episode, criterion):

    # Initialize training:
    model.train()

    # Collect all episode images w/labels:
    image_batch, label_batch = train_loader.__iter__().__next__()

    image_batch_sequence = torch.cat([images for images in image_batch])
    label_batch_sequence = torch.cat([labels for labels in label_batch]).type(torch.LongTensor)

    
    image_batch_sequence = image_batch_sequence.squeeze().view(args.episode_size, args.batch_size, -1)
    label_batch_sequence = Variable(label_batch_sequence.view(-1, args.batch_size))

    # Episode Statistics:
    episode_loss = 0.0
    episode_optimized = 0.0
    episode_correct = 0.0
    episode_predict = 0.0
    episode_optimized = 0.0
    episode_iter = 0.0
    total_loss = 0.0

    # Create initial state:
    initial_state_batch = []
    label_dict = []
    for i in range(args.batch_size):
        label_dict.append({})
        initial_state_batch.append([0 for i in range(args.class_vector_size)])

    state_batch = []
    for j in range(args.episode_size - 1):
        for i in range(args.batch_size):
            state_batch.append([1 if label == label_batch_sequence[j][i].data[0] else 0 for label in range(args.class_vector_size)])


    initial_state_batch = torch.Tensor(initial_state_batch)
    state_batch = torch.Tensor(state_batch) 

    # Creating states:
    episode_pre_states = torch.cat((initial_state_batch, state_batch)).view(args.episode_size, args.batch_size, -1)
    episode_states = torch.cat((episode_pre_states, image_batch_sequence), 2)

    # Initialize model between each episode:
    hidden = model.reset_hidden(args.batch_size)

    predictions, hidden = model(Variable(episode_states), hidden, seq=args.episode_size)

    loss = 0
    for e in range(args.episode_size):
        loss += criterion(predictions[e], label_batch_sequence[e])

    optimizer.zero_grad()

    loss.backward()

    optimizer.step()

    # Accuracy statistics:
    for v in accuracy_dict.values():
        v.append([])

    for i in range(args.episode_size):
        for i_e in range(args.batch_size):

            true_label = label_batch_sequence[i][i_e].data[0]

            # Logging label occurences:
            if (true_label not in label_dict[i_e]):
                label_dict[i_e][true_label] = 1
            else:
                label_dict[i_e][true_label] += 1

        actions = predictions.data[i].max(1)[1].squeeze()

        for i_e in range(args.batch_size):

            true_label = label_batch_sequence[i][i_e].data[0]

            # Logging accuracy:
            if (actions[i_e] == true_label):
                episode_correct += 1.0
                episode_predict += 1.0
                if (label_dict[i_e][true_label] in accuracy_dict):
                    accuracy_dict[label_dict[i_e][true_label]][-1].append(1)
            else:
                episode_predict += 1.0
                if (label_dict[i_e][true_label] in accuracy_dict):
                    accuracy_dict[label_dict[i_e][true_label]][-1].append(0)

    # More status update:
    total_loss = loss.data[0]


    print("\n--- Epoch " + str(epoch) + ", Episode " + str(episode + i + 1) + " Statistics ---")
    print("Instance\tAccuracy")       
    for key in accuracy_dict.keys():
        predictions = accuracy_dict[key][-1]

        amount_correct = sum(predictions)
        amount_predicted = len(predictions)
        probability = float(amount_correct / amount_predicted)
        print("Instance " + str(key) + ":\t" + str(100.0*probability)[0:4] + " %")
    

    # Even more status update:
    print("\n+------------------STATISTICS----------------------+")
    total_accuracy = float((100.0 * episode_correct) / episode_predict)
    print("Batch Average Accuracy = " + str(total_accuracy)[:5] +  " %")
    total_loss = float(total_loss)
    print("Batch Average Loss = " + str(total_loss)[:5])
    print("+--------------------------------------------------+\n")

    ### LOGGING TO TENSORBOARD ###
    data = {
        'training_total_accuracy': total_accuracy,
        'training_total_loss': total_loss,
    }

    for tag, value in data.items():
        writer.scalar_summary(tag, value, epoch)
    ### DONE LOGGING ###

    return total_accuracy, total_loss, accuracy_dict